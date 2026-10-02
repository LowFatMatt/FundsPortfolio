#!/usr/bin/env python3
"""Enrich the 40 compass-CSV stub funds in funds_database.json.

Stubs (source == "csv_20260928") carry only isin/ticker/name/provider/fee/
valid_for. The decision engine's Step 0 required-fields filter needs isin,
name, yearly_fee, sharpe_ratio, max_drawdown, (srri | risk_level) and
volatility — so unenriched stubs can never be selected.

Enrichment precedence per stub:
  1. Merge from data/funds/{ISIN}.json (factsheetslive / yfinance schema v2):
       volatility / max_drawdown  — best available horizon, fraction → percent
                                    (max_drawdown stored positive, DB convention)
       sharpe_ratio               — best available horizon, plain ratio
       srri / risk_level          — from the file's `sri`
       region / theme / ter       — as-is ('NONE'/null kept as "no value")
       asset_class / categories   — name heuristics (every inference is
                                    reported for review)
       is_etf                     — name heuristic ("UCITS ETF" etc.)
  2. Metrics still missing → SRRI-proxy fallback (same maps and sharpe
     placeholder as scripts/backfill_general_metrics.py), flagged in `notes`.
  3. Stubs without an ISIN (4 of 40) cannot be enriched — flagged
     `manual_isin_research_required` in `notes` and listed for lookup.

Idempotent: only null/empty fields are filled; existing values never change.
Atomic write; `--dry-run` (default) reports only.

Usage:
  python scripts/enrich_stubs.py                 # dry-run report
  python scripts/enrich_stubs.py --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from funds_portfolio.portfolio.decision_engine import (  # noqa: E402
    SRRI_MDD_PROXY,
    SRRI_VOL_PROXY,
)

DB_PATH = os.path.join(ROOT, "funds_database.json")
FUNDS_DIR = os.path.join(ROOT, "data", "funds")
STUB_SOURCE = "csv_20260928"
SHARPE_PROXY = 0.5  # neutral placeholder, same as backfill_general_metrics.py
DEFAULT_SRRI = 4

HORIZONS = ("3y", "5y", "1y")  # prefer longer (more stable) horizons

BOND_HINTS = (
    "renten", "bond", "anleih", "corporate", "sovereign", "tresor",
    "variozins", "staatsanleih", "geldmarkt", "money market",
)
EQUITY_HINTS = (
    "aktien", "equity", "msci", "s&p", "nasdaq", "stoxx", "dividenden",
    "champions", "megatrends", "emerging", "health", "defense", "water",
    "energy", "smaller companies", "quality", "global warming", "400 select",
)
MIXED_HINTS = (
    "multi asset", "strategie", "garant", "flex", "protect", "lifestrategy",
    "portfolio fund", "basisanlage", "basisstrategie", "altersvorsorge",
    "ausgewogen", "moderat", "dynamik", "zukunft", "smart power",
)
COMMODITY_HINTS = ("commodity", "rohstoff")


def _norm(text: Optional[str]) -> str:
    return " ".join(str(text or "").lower().split())


def _asset_class_from_name(name: str) -> Optional[str]:
    n = _norm(name)
    if any(h in n for h in COMMODITY_HINTS):
        return "commodity"
    if any(h in n for h in EQUITY_HINTS):
        return "equity"
    if any(h in n for h in MIXED_HINTS):
        return "mixed"
    if any(h in n for h in BOND_HINTS):
        return "bond"
    return None


def _is_etf_from_name(name: str) -> bool:
    n = _norm(name)
    return "ucits etf" in n or " etf" in n or n.startswith("etf ")


def _best_horizon(d: Optional[Dict[str, Any]]) -> Optional[float]:
    if not d:
        return None
    for key in HORIZONS:
        v = d.get(key)
        if v is not None:
            return v
    return None


def _load_per_isin(isin: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(FUNDS_DIR, f"{isin.upper()}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! failed to read {path}: {exc}", file=sys.stderr)
        return None


def _fill(fund: Dict[str, Any], key: str, value: Any) -> bool:
    """Set fund[key] = value only when the current value is null/empty."""
    if value is None:
        return False
    current = fund.get(key)
    if current not in (None, "", []):
        return False
    fund[key] = value
    return True


def _enrich_from_file(fund: Dict[str, Any], ts: Dict[str, Any]) -> List[str]:
    """Merge schema-v2 per-ISIN data into the stub. Returns filled fields."""
    filled: List[str] = []

    vol = _best_horizon(ts.get("volatility"))
    if vol is not None and _fill(fund, "volatility", round(vol * 100.0, 4)):
        filled.append("volatility")

    mdd = _best_horizon((ts.get("risk_metrics") or {}).get("max_drawdown"))
    if mdd is not None and _fill(fund, "max_drawdown", round(abs(mdd) * 100.0, 4)):
        filled.append("max_drawdown")

    sharpe = _best_horizon((ts.get("risk_metrics") or {}).get("sharpe"))
    if sharpe is not None and _fill(fund, "sharpe_ratio", sharpe):
        filled.append("sharpe_ratio")

    sri = ts.get("sri")
    if sri is not None:
        if _fill(fund, "srri", max(1, min(7, int(sri)))):
            filled.append("srri")
        if _fill(fund, "risk_level", max(1, min(5, int(sri) - 1))):
            filled.append("risk_level")

    if ts.get("region") and _fill(fund, "region", ts["region"]):
        filled.append("region")
    if ts.get("theme") and ts["theme"] != "NONE" and _fill(fund, "theme", ts["theme"]):
        filled.append("theme")

    ter = ts.get("ter")
    if ter is not None and _fill(fund, "yearly_fee", round(ter * 100.0, 4)):
        filled.append("yearly_fee")

    # is_etf=False is a valid DB value, so bypass _fill() — the name heuristic
    # may legitimately flip a hardcoded False from the stub builder to True.
    if not fund.get("is_etf") and _is_etf_from_name(fund.get("name") or ""):
        fund["is_etf"] = True
        filled.append("is_etf")

    # asset_class from the dominant breakdown key when available, else name
    breakdown = ts.get("asset_class_breakdown") or {}
    asset_class = (
        max(breakdown.items(), key=lambda kv: kv[1])[0]
        if breakdown
        else _asset_class_from_name(fund.get("name") or "")
    )
    if asset_class and _fill(fund, "asset_class", asset_class):
        filled.append("asset_class")

    if asset_class and asset_class != "commodity":
        region = fund.get("region") or "global"
        _fill(fund, "categories", [f"{region}_{asset_class}"])

    return filled


def _proxy_fill(fund: Dict[str, Any]) -> List[str]:
    """SRRI-proxy fallback for metrics still missing (backfill semantics)."""
    srri = fund.get("srri") or fund.get("risk_level") or DEFAULT_SRRI
    srri = max(1, min(7, int(srri)))
    filled: List[str] = []

    if _fill(fund, "volatility", SRRI_VOL_PROXY.get(srri)):
        filled.append("volatility*")
    if _fill(fund, "max_drawdown", SRRI_MDD_PROXY.get(srri)):
        filled.append("max_drawdown*")
    if _fill(fund, "sharpe_ratio", SHARPE_PROXY):
        filled.append("sharpe_ratio*")
    if not (fund.get("srri") or fund.get("risk_level")):
        if _fill(fund, "srri", srri):
            filled.append(f"srri*={srri}")
        if _fill(fund, "risk_level", max(1, min(5, srri - 1))):
            filled.append(f"risk_level*={srri - 1}")
    return filled


def _missing_required(fund: Dict[str, Any]) -> List[str]:
    """Fields the engine's Step 0 required-fields filter insists on."""
    missing = [
        k
        for k in ("yearly_fee", "sharpe_ratio", "max_drawdown", "volatility")
        if not fund.get(k)
    ]
    if not (fund.get("srri") or fund.get("risk_level")):
        missing.append("srri_or_risk_level")
    return missing


def enrich_stubs(db_path: str, dry_run: bool = True, write_report: Optional[str] = None) -> int:
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    funds = data.get("funds_database", [])
    stubs = [f for f in funds if f.get("source") == STUB_SOURCE]

    from_file: List[str] = []
    proxied: List[str] = []
    complete: List[str] = []
    incomplete: List[str] = []
    no_isin: List[str] = []

    for fund in stubs:
        name = f"{fund.get('name')} ({fund.get('isin') or 'no ISIN'})"
        isin = fund.get("isin")
        if not isin:
            note = "manual_isin_research_required: no ISIN in compass CSV"
            if note not in (fund.get("notes") or ""):
                fund["notes"] = f"{fund.get('notes') or ''} {note}".strip()
            no_isin.append(name)
            continue

        ts = _load_per_isin(isin)
        if ts:
            filled = _enrich_from_file(fund, ts)
            if filled:
                from_file.append(f"  ~ {name}: +{', '.join(filled)}")

        proxied_fields = _proxy_fill(fund)
        if proxied_fields:
            proxied.append(f"  * {name}: proxy {', '.join(proxied_fields)}")

        missing = _missing_required(fund)
        if missing:
            incomplete.append(f"  ! {name}: still missing {', '.join(missing)}")
        else:
            complete.append(name)
            if "Stub from compass CSV import" in (fund.get("notes") or ""):
                if proxied_fields:
                    fund["notes"] = (
                        "Imported from compass CSV; metrics partially SRRI-proxied "
                        "(marked with * in the enrichment report), pending factsheet data."
                    )
                else:
                    fund["notes"] = (
                        "Imported from compass CSV; enriched from per-ISIN scrape/yfinance."
                    )

    lines = [f"Stub enrichment — {db_path} ({'DRY RUN' if dry_run else 'WRITTEN'})"]
    lines.append(f"  Stubs found: {len(stubs)}")
    lines.append(f"  Engine-complete after enrichment: {len(complete)}/{len(stubs)}")
    lines.append(f"  Fields merged from data/funds/{{ISIN}}.json: {len(from_file)}")
    lines.extend(from_file)
    lines.append(f"  SRRI-proxy filled (* = proxy value): {len(proxied)}")
    lines.extend(proxied)
    lines.append(f"  Stubs without ISIN (manual research): {len(no_isin)}")
    lines.extend(f"  ? {n}" for n in no_isin)
    lines.append(f"  Still engine-incomplete: {len(incomplete)}")
    lines.extend(incomplete)

    report = "\n".join(lines)
    print(report)
    if write_report:
        with open(write_report, "w", encoding="utf-8") as f:
            f.write(report + "\n")

    if dry_run:
        print("\n[dry-run] No changes written. Pass --write to apply.")
        return 0

    tmp = db_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, db_path)
    print(f"\nWritten {db_path}: {len(complete)}/{len(stubs)} stubs engine-complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db_path", nargs="?", default=DB_PATH)
    parser.add_argument("--write", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--report-file", default=None, help="Also write the report to this path")
    args = parser.parse_args()
    return enrich_stubs(args.db_path, dry_run=not args.write, write_report=args.report_file)


if __name__ == "__main__":
    sys.exit(main())
