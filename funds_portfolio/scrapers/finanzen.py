from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urljoin

from .base import FundScraper, _normalize_percent, _strip_html, load_i18n_asset_map


class FinanzenNetScraper(FundScraper):
    def __init__(self):
        self.translator = load_i18n_asset_map()

    def _find_chart_labels_values(self, html: str, base_url: str) -> Optional[Dict[str, float]]:
        # Find chart.aspx URLs and parse labels/values query params
        for match in re.finditer(r'https?://[^"\']*chart\.aspx\?[^"\']+', html):
            url = match.group(0)
            qs = parse_qs(url.split("?", 1)[1])
            labels = qs.get("labels") or qs.get("label") or []
            values = qs.get("values") or qs.get("value") or []
            if not labels or not values:
                continue
            labs = labels[0].split(";")
            vals = values[0].split(";")
            if len(labs) != len(vals):
                continue
            out: Dict[str, float] = {}
            for l, v in zip(labs, vals):
                try:
                    out[l.strip()] = float(v)
                except Exception:
                    try:
                        out[l.strip()] = float(v.replace(",", "."))
                    except Exception:
                        continue
            if out:
                return out
        return None

    def _extract_number_after_label(self, html: str, labels: List[str]) -> Optional[float]:
        text = _strip_html(html)
        for label in labels:
            # search for label followed by a percent
            pattern = rf"{re.escape(label)}[^0-9%\n\r]{{0,40}}([0-9]+[\.,][0-9]+)\s*%"
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return _normalize_percent(m.group(1))
        return None

    def _extract_sharpe(self, html: str) -> Optional[float]:
        text = _strip_html(html)
        # collect candidates with horizon tags
        candidates: Dict[str, float] = {}
        for m in re.finditer(r"(5y|5 Jahre|3y|3 Jahre|1y|1 Jahr)[^0-9]{0,30}([\-]?[0-9]+[\.,][0-9]+)", text, flags=re.IGNORECASE):
            horizon = m.group(1).lower()
            val = _normalize_percent(m.group(2))
            if val is not None:
                candidates[horizon] = val
        # prefer 5y > 3y > 1y
        for key in ("5y", "5 jahre", "3y", "3 jahre", "1y", "1 jahr"):
            if key in candidates:
                return candidates[key]
        # fallback: look for 'Sharpe' and a nearby number
        for m in re.finditer(r"Sharpe[^0-9\-]{0,40}([\-]?[0-9]+[\.,][0-9]+)", text, flags=re.IGNORECASE):
            val = m.group(1)
            try:
                return float(val.replace(",", "."))
            except Exception:
                continue
        return None

    def _extract_srri(self, html: str) -> Optional[int]:
        text = _strip_html(html)
        m = re.search(r"SRRI[^0-9]{0,10}([1-5])", text, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(r"Risikoklasse[^0-9]{0,10}([1-5])", text, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def _extract_max_drawdown(self, html: str) -> Optional[float]:
        text = _strip_html(html)
        # Look for 'Max' + drawdown or 'Max Drawdown' or 'Max. Drawdown' patterns
        m = re.search(r"Max(?:\.|imum)?\s*(?:Drawdown|DD|Draw-down|Rückgang)[^0-9\-]{0,40}([\-]?[0-9]+[\.,][0-9]+)\s*%", text, flags=re.IGNORECASE)
        if m:
            val = m.group(1)
            try:
                return abs(float(val.replace(",", ".")))
            except Exception:
                return None
        # fallback: look for 'Max. Verlust' or 'Maximaler Verlust'
        m = re.search(r"Max(?:\.|imal)?[^0-9]{0,20}Verlust[^0-9\-]{0,40}([\-]?[0-9]+[\.,][0-9]+)\s*%", text, flags=re.IGNORECASE)
        if m:
            try:
                return abs(float(m.group(1).replace(",", ".")))
            except Exception:
                return None
        return None

    def _detect_is_etf(self, html: str) -> Optional[bool]:
        if re.search(r"\bETF\b", html, flags=re.IGNORECASE):
            return True
        return False

    def _extract_esg(self, html: str) -> Dict:
        out = {"esg_label": None, "esg_article_8": None, "esg_article_9": None}
        text = html or ""
        if re.search(r"SFDR|Artikel\s*8|Article\s*8", text, flags=re.IGNORECASE):
            out["esg_article_8"] = True
            out["esg_label"] = "SFDR_ARTICLE_8"
        if re.search(r"Artikel\s*9|Article\s*9", text, flags=re.IGNORECASE):
            out["esg_article_9"] = True
            out["esg_label"] = "SFDR_ARTICLE_9"
        return out

    def extract_all(self, html: str, base_url: str) -> Dict:
        """Extract relevant metrics from a finanzen.net fund page.

        Returns a dict with keys: yearly_fee, volatility, max_drawdown, sharpe_ratio,
        srri, asset_class_breakdown_raw, asset_class_breakdown_translated, is_etf,
        esg_label, esg_article_8, esg_article_9
        """
        result: Dict = {}
        # fee
        fee = self._extract_number_after_label(html, ["Laufende Kosten", "Gesamtkostenquote", "Total Expense Ratio", "TER"]) or None
        if fee is not None:
            result["yearly_fee"] = round(float(fee), 4)

        # volatility (prefer 3y)
        vol = self._extract_number_after_label(html, ["Volatilität 3 Jahre", "Volatilität 1 Jahr", "Volatilität"])
        if vol is not None:
            result["volatility"] = round(float(vol), 4)

        # max drawdown
        mdd = self._extract_max_drawdown(html)
        if mdd is not None:
            result["max_drawdown"] = round(float(mdd), 4)

        # sharpe
        sharpe = self._extract_sharpe(html)
        if sharpe is not None:
            # sharpe might be a ratio, not percent
            result["sharpe_ratio"] = round(float(sharpe), 6)

        # srri
        srri = self._extract_srri(html)
        if srri is not None:
            result["srri"] = int(srri)

        # asset breakdown
        breakdown = self._find_chart_labels_values(html, base_url)
        if breakdown:
            result["asset_class_breakdown_raw"] = breakdown
            # translated
            translated = {}
            for k, v in breakdown.items():
                key = self.translator.get(k.strip().lower())
                if key:
                    translated[key] = v
            if translated:
                result["asset_class_breakdown_translated"] = translated

        # ETF detection
        result["is_etf"] = self._detect_is_etf(html)

        # ESG
        esg = self._extract_esg(html)
        result.update(esg)

        return result
