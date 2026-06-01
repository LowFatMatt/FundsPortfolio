#!/usr/bin/env python3
"""
Sync factsheetslive product pages into data/funds/{ISIN}.json.

Cache-first model: this script runs OFFLINE and writes JSON files that the
Flask app reads at runtime. No live scraping at request time.

Re-run after a few weeks to refresh metrics; existing files are replaced
atomically.

Usage:
    python scripts/sync_factsheetslive.py \\
        --base-url https://provinzial-nord.stg.wt.factsheetslive.com \\
        --sample 10

    python scripts/sync_factsheetslive.py --isin-file isins.txt --output data/funds/

Limitations:
    Selectors are heuristic — they target row labels (e.g. "1 Jahr",
    "Volatilität 3 Jahre", "Sharpe Ratio"). If the upstream layout changes,
    the parser leaves the affected field null and continues.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 is required. Install with: pip install beautifulsoup4")
    sys.exit(1)

# Ensure the scripts/ dir is on sys.path so sibling helper modules import cleanly
# whether this file is invoked as `python scripts/sync_factsheetslive.py` or
# `python -m scripts.sync_factsheetslive` (the former adds scripts/ for us; the
# latter adds the repo root and needs the explicit insertion).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _german_labels import (  # noqa: E402
    canonical_asset_class_from_breakdown_key as _canonical_asset_class,
    region_from_german as _region_from_german,
    theme_from_german as _theme_from_german,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "funds"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_CATALOG    = REPO_ROOT / "funds_database.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sync_factsheetslive")


# ---------- HTTP ----------

def make_session(user_agent: str, timeout: int) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    s.request = _with_timeout(s.request, timeout)  # type: ignore[assignment]
    return s


def _with_timeout(fn, timeout):
    def wrapper(method, url, **kw):
        kw.setdefault("timeout", timeout)
        return fn(method, url, **kw)
    return wrapper


# ---------- Parsing helpers ----------

SIGNED_NUM_RE = re.compile(r"(-?\d+(?:[\.,]\d+)?)")


def _to_float(text: Optional[str]) -> Optional[float]:
    """Parse a German-formatted number ('1,29' or '-5,25%') into a float."""
    if text is None:
        return None
    t = text.strip().replace("\xa0", "").replace(" ", "")
    if not t or t in ("–", "-", "—", "n/a", "N/A"):
        return None
    m = SIGNED_NUM_RE.search(t.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _pct_to_frac(text: Optional[str]) -> Optional[float]:
    """Parse a percentage string into a fraction ('1,29%' → 0.0129)."""
    v = _to_float(text)
    if v is None:
        return None
    return round(v / 100.0, 6)


# --- Embedded JSON blobs (data-price-series, data-risiko-rendite) ---

def _extract_data_attr_json(html: str, attr: str) -> Optional[Any]:
    """Pull a JSON blob out of an HTML element attribute value."""
    m = re.search(rf'{attr}="([^"]+)"', html)
    if not m:
        return None
    try:
        return json.loads(html_lib.unescape(m.group(1)))
    except (ValueError, json.JSONDecodeError):
        return None


def extract_current_risk_rendite(html: str, isin: str) -> Optional[Dict[str, Any]]:
    """
    data-risiko-rendite is a list of {name, isin, performances, volatilities,
    provinzialFundType, isCurrent}. Return the entry matching this ISIN
    (or the isCurrent=True entry as a fallback).
    """
    blob = _extract_data_attr_json(html, "data-risiko-rendite")
    if not isinstance(blob, list):
        return None
    target = isin.upper()
    for entry in blob:
        if (entry.get("isin") or "").upper() == target:
            return entry
    for entry in blob:
        if entry.get("isCurrent"):
            return entry
    return None


def extract_price_series_monthly(html: str) -> List[Dict[str, Any]]:
    """
    data-price-series is the full daily NAV history. Downsample to month-end
    values and rebase so the first point equals 100.
    """
    blob = _extract_data_attr_json(html, "data-price-series")
    if not isinstance(blob, list) or not blob:
        return []
    by_month: Dict[str, Tuple[str, float]] = {}
    for point in blob:
        d = point.get("date")
        v = point.get("value")
        if not d or v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        try:
            parsed = date.fromisoformat(d)
        except ValueError:
            continue
        key = f"{parsed.year:04d}-{parsed.month:02d}"
        existing = by_month.get(key)
        if existing is None or d > existing[0]:
            by_month[key] = (d, v)

    series = [(d, v) for (d, v) in by_month.values()]
    series.sort(key=lambda p: p[0])
    if not series:
        return []
    base = series[0][1] or 1.0
    return [{"d": d, "v": round(v / base * 100.0, 4)} for (d, v) in series]


# --- HTML tables (performance row + risk metrics row-major) ---

PERFORMANCE_HEADERS_TO_KEY = {
    "3 monate":        "3m",
    "6 monate":        "6m",
    "lfd. jahr":       "ytd",
    "1 jahr":          "1y",
    "3 jahre p.a.":    "3y_pa",
    "5 jahre p.a.":    "5y_pa",
    "10 jahre p.a.":   "10y_pa",
    "seit auflage p.a.":"si_pa",
}


def parse_performance_table(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    """
    Find the Wertentwicklung table whose <thead> has columns like
    '3 Monate', '6 Monate', ..., 'seit Auflage p.a.' and the single tbody
    row carries the values. Map by header → period key.
    """
    out = {k: None for k in PERFORMANCE_HEADERS_TO_KEY.values()}
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers or "3 monate" not in headers:
            continue
        body_rows = table.find("tbody").find_all("tr") if table.find("tbody") else []
        if not body_rows:
            continue
        values = [td.get_text(strip=True) for td in body_rows[0].find_all("td")]
        for header, raw in zip(headers, values):
            key = PERFORMANCE_HEADERS_TO_KEY.get(header.strip())
            if key:
                out[key] = _pct_to_frac(raw)
        return out
    return out


def parse_risk_table(soup: BeautifulSoup) -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """
    Parse the 'Kennzahlen' table (row-major: row label = metric, columns =
    1Y/3Y/5Y in order). Returns (volatility, sharpe, max_drawdown).
    """
    vol = {"1y": None, "3y": None, "5y": None}
    sharpe = {"1y": None, "3y": None, "5y": None}
    mdd = {"1y": None, "3y": None, "5y": None}
    order = ("1y", "3y", "5y")

    for table in soup.find_all("table"):
        text_first_col = [
            (row.find_all(["td", "th"])[0].get_text(strip=True).lower() if row.find_all(["td", "th"]) else "")
            for row in table.find_all("tr")
        ]
        if not any("sharpe" in c for c in text_first_col):
            continue
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            label = cells[0].get_text(strip=True).lower()
            values = [c.get_text(strip=True) for c in cells[1:4]]
            if "volatil" in label:
                for k, raw in zip(order, values):
                    vol[k] = _pct_to_frac(raw)
            elif "sharpe" in label:
                for k, raw in zip(order, values):
                    sharpe[k] = _to_float(raw)
            elif "drawdown" in label or "max" in label:
                for k, raw in zip(order, values):
                    mdd[k] = _pct_to_frac(raw)
        return vol, sharpe, mdd
    return vol, sharpe, mdd


# --- Allocation sections (asset class breakdown + top holdings) ---

def _parse_allocation_section(soup: BeautifulSoup, heading_substr: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Find a <details><summary>{heading}</summary><div class="portfolioallokation-content">...
    that contains <div class="allocation-bar-row"> entries with label and value spans.
    """
    out: List[Dict[str, Any]] = []
    for details in soup.find_all("details"):
        summary = details.find("summary")
        if not summary:
            continue
        if heading_substr.lower() not in summary.get_text(strip=True).lower():
            continue
        for row in details.find_all("div", class_="allocation-bar-row"):
            label_el = row.find("span", class_="allocation-bar-label")
            value_el = row.find("span", class_="allocation-bar-value")
            if not label_el or not value_el:
                continue
            name = label_el.get_text(" ", strip=True)
            weight = _pct_to_frac(value_el.get_text(strip=True))
            if name and weight is not None:
                out.append({"name": name, "weight": weight})
            if limit and len(out) >= limit:
                break
        return out
    return out


def parse_asset_class_breakdown(soup: BeautifulSoup) -> Dict[str, float]:
    """
    Parse the 'Vermögensaufteilung' section into a normalized
    {asset_class_key: weight} mapping. Provinzial labels are German
    free-text; we collapse them into our canonical keys.
    """
    raw = _parse_allocation_section(soup, "Vermögensaufteilung")
    if not raw:
        return {}
    bucketed: Dict[str, float] = {}
    for entry in raw:
        key = _canonical_asset_class(entry["name"])
        bucketed[key] = round(bucketed.get(key, 0.0) + entry["weight"], 6)
    return bucketed


def parse_top_holdings(soup: BeautifulSoup, limit: int = 10) -> List[Dict[str, Any]]:
    """Top 10 Positionen section (same allocation-bar markup)."""
    return _parse_allocation_section(soup, "Top 10 Positionen", limit=limit)


# --- Stammdaten table (label-then-value row layout) ---

def _stammdaten_lookup(soup: BeautifulSoup, label_patterns: List[str]) -> Optional[str]:
    """
    Find a <tr> whose first cell text contains one of the patterns and
    return the next cell's text.
    """
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).lower()
        for pat in label_patterns:
            if pat.lower() in label:
                return cells[1].get_text(" ", strip=True)
    return None


def parse_currency_and_asof(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    currency = _stammdaten_lookup(soup, ["Fondswährung", "Fund Currency"])
    if currency:
        m = re.search(r"\b([A-Z]{3})\b", currency)
        currency = m.group(1) if m else currency.strip()[:3].upper()
    raw_as_of = _stammdaten_lookup(soup, ["TER (Stand", "Stand:"])
    as_of: Optional[str] = None
    if raw_as_of:
        m = re.search(r"(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})", raw_as_of)
        if m:
            raw = m.group(1)
            if "." in raw:
                dd, mm, yy = raw.split(".")
                as_of = f"{yy}-{mm}-{dd}"
            else:
                as_of = raw
    return currency, as_of


def parse_region_theme(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    Read the Stammdaten 'Region' and 'Thema' rows and map the German free-text
    to our canonical region/theme keys. Region defaults to 'global', theme to
    'NONE' when the page leaves the field blank or shows a dash.
    """
    region_raw = _stammdaten_lookup(soup, ["Region"])
    theme_raw = _stammdaten_lookup(soup, ["Thema", "Anlagethema"])
    return _region_from_german(region_raw), _theme_from_german(theme_raw)


def parse_ter_and_sri(soup: BeautifulSoup) -> Tuple[Optional[float], Optional[int]]:
    ter_raw = _stammdaten_lookup(soup, ["TER", "Laufende Kosten"])
    ter = _pct_to_frac(ter_raw) if ter_raw else None
    sri_raw = _stammdaten_lookup(soup, ["Risikoklasse", "SRI", "SRRI"])
    sri: Optional[int] = None
    if sri_raw:
        m = re.search(r"\b([1-7])\b", sri_raw)
        if m:
            sri = int(m.group(1))
    return ter, sri


# ---------- Pipeline ----------

def fetch_product(session: requests.Session, base_url: str, isin: str, detail_path: str) -> Optional[str]:
    url = base_url.rstrip("/") + detail_path.replace("{isin}", isin)
    try:
        r = session.get(url)
    except requests.RequestException as exc:
        logger.warning("%s: HTTP error: %s", isin, exc)
        return None
    if r.status_code != 200:
        logger.warning("%s: status %s", isin, r.status_code)
        return None
    return r.text


def build_fund_record(isin: str, html: str, source_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    currency, as_of = parse_currency_and_asof(soup)
    ter, sri = parse_ter_and_sri(soup)
    region, theme = parse_region_theme(soup)

    # Performance: prefer the 8-column HTML table (covers 3m/6m/ytd/1y/3y_pa/5y_pa/10y_pa/si_pa);
    # fall back to data-risiko-rendite for the periods it covers (ytd/1y/3y/5y/10y).
    perf_periods = parse_performance_table(soup)
    vol, sharpe, mdd = parse_risk_table(soup)

    rr_entry = extract_current_risk_rendite(html, isin) or {}
    rr_perf = rr_entry.get("performances") or {}
    rr_vol  = rr_entry.get("volatilities") or {}
    # data-risiko-rendite keys are ytd/1y/3y/5y/10y. Treat 3y/5y/10y as p.a. (matches table headers).
    rr_mapping_perf = {"ytd": "ytd", "1y": "1y", "3y": "3y_pa", "5y": "5y_pa", "10y": "10y_pa"}
    for src, dst in rr_mapping_perf.items():
        if perf_periods.get(dst) is None and rr_perf.get(src) is not None:
            perf_periods[dst] = round(float(rr_perf[src]), 6)
    rr_mapping_vol = {"1y": "1y", "3y": "3y", "5y": "5y"}
    for src, dst in rr_mapping_vol.items():
        if vol.get(dst) is None and rr_vol.get(src) is not None:
            vol[dst] = round(float(rr_vol[src]), 6)

    nav_series = extract_price_series_monthly(html)
    holdings   = parse_top_holdings(soup)
    breakdown  = parse_asset_class_breakdown(soup)

    record: Dict[str, Any] = {
        "isin": isin.upper(),
        "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
        "schema_version": 2,
        "source": "factsheetslive",
        "source_url": source_url,
        "currency": currency or "EUR",
        "fund_name": rr_entry.get("name"),
        "provinzial_fund_type": rr_entry.get("provinzialFundType"),
        "region": region,
        "theme": theme,
        "ter": ter,
        "sri": sri,
        "performance": {
            "periods": perf_periods,
            "nav_series": nav_series,
        },
        "volatility": vol,
        "risk_metrics": {"sharpe": sharpe, "max_drawdown": mdd},
        "asset_class_breakdown": breakdown,
        "top_holdings": holdings,
    }
    return record


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def has_any_data(record: Dict[str, Any]) -> bool:
    perf = record.get("performance", {}).get("periods") or {}
    vol  = record.get("volatility") or {}
    rm   = record.get("risk_metrics") or {}
    return any(v is not None for v in perf.values()) \
        or any(v is not None for v in vol.values()) \
        or any(v is not None for d in rm.values() for v in (d or {}).values()) \
        or bool(record.get("top_holdings")) \
        or bool(record.get("asset_class_breakdown")) \
        or bool((record.get("performance") or {}).get("nav_series"))


def load_isins(catalog_path: Path, override_file: Optional[Path], sample: Optional[int]) -> List[str]:
    if override_file:
        isins = []
        for line in override_file.read_text(encoding="utf-8").splitlines():
            isin = line.split("#", 1)[0].strip()
            if isin:
                isins.append(isin.upper())
    else:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        isins = [f["isin"].upper() for f in data.get("funds_database", []) if f.get("isin")]
    if sample:
        isins = isins[:sample]
    return isins


def write_reports(results: List[Dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp": ts,
        "total": len(results),
        "written": sum(1 for r in results if r["status"] == "written"),
        "empty":   sum(1 for r in results if r["status"] == "empty"),
        "failed":  sum(1 for r in results if r["status"] == "failed"),
    }

    json_path = output_dir / f"sync_factsheetslive_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    logger.info("Report: %s", json_path)

    md_path = output_dir / f"sync_factsheetslive_{ts}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# factsheetslive Sync Report\n\n")
        f.write(f"**Run:** {ts}\n\n")
        f.write(f"- Written: {summary['written']}\n")
        f.write(f"- Empty (no parseable data): {summary['empty']}\n")
        f.write(f"- Failed (HTTP/parse error): {summary['failed']}\n\n")
        if summary["empty"]:
            f.write("## ISINs with no parseable data — investigate selectors\n\n")
            for r in results:
                if r["status"] == "empty":
                    f.write(f"- {r['isin']}: {r.get('reason', '')}\n")
        if summary["failed"]:
            f.write("\n## ISINs with errors\n\n")
            for r in results:
                if r["status"] == "failed":
                    f.write(f"- {r['isin']}: {r.get('reason', '')}\n")
    logger.info("QC checklist: %s", md_path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="https://provinzial-nord.stg.wt.factsheetslive.com",
                        help="factsheetslive base URL (customer-specific)")
    parser.add_argument("--detail-path", default="/produkt/{isin}",
                        help="URL path template for product pages")
    parser.add_argument("--isin-file", type=Path, default=None,
                        help="Optional file with one ISIN per line; default reads from funds_database.json")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG,
                        help="Path to funds_database.json")
    parser.add_argument("--sample", type=int, default=None, help="Only process the first N ISINs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Output directory for per-ISIN JSON files")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR,
                        help="Output directory for run reports")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    parser.add_argument("--user-agent", default="FundsPortfolio/1.0 (offline ingestion)")
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write files")
    args = parser.parse_args(argv)

    isins = load_isins(args.catalog, args.isin_file, args.sample)
    logger.info("Processing %d ISINs from %s", len(isins),
                args.isin_file or args.catalog)

    session = make_session(args.user_agent, args.timeout)
    results: List[Dict[str, Any]] = []

    for i, isin in enumerate(isins, 1):
        logger.info("[%d/%d] %s", i, len(isins), isin)
        source_url = args.base_url.rstrip("/") + args.detail_path.replace("{isin}", isin)
        html = fetch_product(session, args.base_url, isin, args.detail_path)
        if not html:
            results.append({"isin": isin, "status": "failed", "reason": "no HTML / non-200"})
        else:
            try:
                record = build_fund_record(isin, html, source_url)
            except (ValueError, AttributeError) as exc:
                results.append({"isin": isin, "status": "failed", "reason": f"parse error: {exc}"})
            else:
                if not has_any_data(record):
                    results.append({"isin": isin, "status": "empty", "reason": "no fields matched selectors"})
                else:
                    if not args.dry_run:
                        atomic_write_json(args.output / f"{isin}.json", record)
                    results.append({"isin": isin, "status": "written",
                                    "fields_present": _summarise_present_fields(record)})

        if i < len(isins) and args.delay > 0:
            time.sleep(args.delay)

    write_reports(results, args.report_dir)
    return 0


def _summarise_present_fields(record: Dict[str, Any]) -> Dict[str, int]:
    perf = record.get("performance", {}).get("periods") or {}
    vol  = record.get("volatility") or {}
    rm   = record.get("risk_metrics") or {}
    return {
        "perf_periods":  sum(1 for v in perf.values() if v is not None),
        "volatility":    sum(1 for v in vol.values()  if v is not None),
        "sharpe":        sum(1 for v in (rm.get("sharpe") or {}).values() if v is not None),
        "max_dd":        sum(1 for v in (rm.get("max_drawdown") or {}).values() if v is not None),
        "holdings":      len(record.get("top_holdings") or []),
        "nav_points":    len((record.get("performance") or {}).get("nav_series") or []),
        "breakdown_keys": len(record.get("asset_class_breakdown") or {}),
        "region":        0 if record.get("region") in (None, "global") else 1,
        "theme":         0 if record.get("theme") in (None, "NONE") else 1,
    }


if __name__ == "__main__":
    sys.exit(main())
