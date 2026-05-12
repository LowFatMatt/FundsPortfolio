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
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 is required. Install with: pip install beautifulsoup4")
    sys.exit(1)

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

PERCENT_RE = re.compile(r"(-?\d+(?:[\.,]\d+)?)\s*%")
SIGNED_NUM_RE = re.compile(r"(-?\d+(?:[\.,]\d+)?)")


def _to_float(text: Optional[str]) -> Optional[float]:
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
    """Parse a percentage string into a fraction (e.g. '1.29%' → 0.0129)."""
    v = _to_float(text)
    if v is None:
        return None
    return round(v / 100.0, 6)


def find_label_value(soup: BeautifulSoup, label_patterns: List[str]) -> Optional[str]:
    """
    Find a table row whose first cell matches one of the label patterns
    (case-insensitive contains). Return the next sibling cell text, or None.
    """
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = (cells[0].get_text(strip=True) or "").lower()
        for pat in label_patterns:
            if pat.lower() in label:
                return cells[1].get_text(" ", strip=True)
    # Also try definition lists
    for dt in soup.find_all("dt"):
        label = (dt.get_text(strip=True) or "").lower()
        for pat in label_patterns:
            if pat.lower() in label:
                dd = dt.find_next_sibling("dd")
                if dd:
                    return dd.get_text(" ", strip=True)
    return None


def parse_performance(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    """
    Extract per-period performance returns. Looks for German and English labels.
    Returns fractions (0.045 not 4.5).
    """
    mapping = [
        ("3m",     ["3 Monate", "3 Months"]),
        ("6m",     ["6 Monate", "6 Months"]),
        ("ytd",    ["lfd. Jahr", "current year", "YTD", "Lfd. Jahr"]),
        ("1y",     ["1 Jahr", "1 Year"]),
        ("3y_pa",  ["3 Jahre p.a.", "3 Years p.a.", "3 Jahre"]),
        ("5y_pa",  ["5 Jahre p.a.", "5 Years p.a.", "5 Jahre"]),
        ("10y_pa", ["10 Jahre p.a.", "10 Years p.a.", "10 Jahre"]),
        ("si_pa",  ["seit Auflage", "Since Inception"]),
    ]
    out: Dict[str, Optional[float]] = {}
    for key, patterns in mapping:
        out[key] = _pct_to_frac(find_label_value(soup, patterns))
    return out


def parse_volatility(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    """
    Volatility is typically in its own labeled section ("Volatilität").
    Try to scope the search to that section first; fall back to global rows.
    """
    section = None
    for header in soup.find_all(["h2", "h3", "h4", "div"]):
        text = (header.get_text(strip=True) or "").lower()
        if "volatil" in text:
            section = header.find_parent() or header
            break
    target = section or soup
    return {
        "1y": _pct_to_frac(find_label_value(target, ["Volatilität 1 Jahr", "1 Year", "1 Jahr"])),
        "3y": _pct_to_frac(find_label_value(target, ["Volatilität 3 Jahre", "3 Years", "3 Jahre"])),
        "5y": _pct_to_frac(find_label_value(target, ["Volatilität 5 Jahre", "5 Years", "5 Jahre"])),
    }


def parse_risk_metrics(soup: BeautifulSoup) -> Dict[str, Dict[str, Optional[float]]]:
    sharpe = {
        "1y": _to_float(find_label_value(soup, ["Sharpe Ratio 1", "Sharpe 1"])),
        "3y": _to_float(find_label_value(soup, ["Sharpe Ratio 3", "Sharpe 3"])),
        "5y": _to_float(find_label_value(soup, ["Sharpe Ratio 5", "Sharpe 5"])),
    }
    mdd = {
        "1y": _pct_to_frac(find_label_value(soup, ["Max. Drawdown 1", "Max Drawdown 1", "Max. Drawdown 1 Jahr"])),
        "3y": _pct_to_frac(find_label_value(soup, ["Max. Drawdown 3", "Max Drawdown 3", "Max. Drawdown 3 Jahre"])),
        "5y": _pct_to_frac(find_label_value(soup, ["Max. Drawdown 5", "Max Drawdown 5", "Max. Drawdown 5 Jahre"])),
    }
    return {"sharpe": sharpe, "max_drawdown": mdd}


def parse_top_holdings(soup: BeautifulSoup, limit: int = 10) -> List[Dict[str, Any]]:
    """Look for a holdings/positions table; return up to `limit` rows."""
    candidates = []
    for table in soup.find_all("table"):
        caption = (table.find("caption").get_text(strip=True).lower()
                   if table.find("caption") else "")
        prev_header = table.find_previous(["h2", "h3", "h4"])
        prev_text = (prev_header.get_text(strip=True).lower() if prev_header else "")
        if "position" in caption or "holding" in caption or "position" in prev_text or "holding" in prev_text:
            candidates.append(table)
    if not candidates:
        return []
    holdings: List[Dict[str, Any]] = []
    table = candidates[0]
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td"])
        if len(cells) < 2:
            continue
        name = cells[0].get_text(" ", strip=True)
        weight_raw = cells[-1].get_text(" ", strip=True)
        weight = _pct_to_frac(weight_raw)
        if name and weight is not None:
            holdings.append({"name": name, "weight": weight})
        if len(holdings) >= limit:
            break
    return holdings


def parse_currency_and_asof(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    """Extract fund currency + as-of date from Stammdaten."""
    currency = find_label_value(soup, ["Fondswährung", "Fund Currency"])
    if currency:
        m = re.search(r"\b([A-Z]{3})\b", currency)
        currency = m.group(1) if m else currency.strip()[:3].upper()
    as_of = find_label_value(soup, ["Stand", "as of", "TER (Stand"])
    if as_of:
        m = re.search(r"(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})", as_of)
        if m:
            raw = m.group(1)
            if "." in raw:
                d, mth, y = raw.split(".")
                as_of = f"{y}-{mth}-{d}"
            else:
                as_of = raw
    return currency, as_of


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
    perf_periods = parse_performance(soup)
    vol          = parse_volatility(soup)
    risk         = parse_risk_metrics(soup)
    holdings     = parse_top_holdings(soup)

    record = {
        "isin": isin.upper(),
        "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
        "schema_version": 1,
        "source": "factsheetslive",
        "source_url": source_url,
        "currency": currency or "EUR",
        "performance": {
            "periods": perf_periods,
            "nav_series": [],  # not derivable from the product page; needs a separate source
        },
        "volatility": vol,
        "risk_metrics": risk,
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
        or bool(record.get("top_holdings"))


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
        "perf_periods": sum(1 for v in perf.values() if v is not None),
        "volatility":   sum(1 for v in vol.values()  if v is not None),
        "sharpe":       sum(1 for v in (rm.get("sharpe") or {}).values() if v is not None),
        "max_dd":       sum(1 for v in (rm.get("max_drawdown") or {}).values() if v is not None),
        "holdings":     len(record.get("top_holdings") or []),
    }


if __name__ == "__main__":
    sys.exit(main())
