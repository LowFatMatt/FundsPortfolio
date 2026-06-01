#!/usr/bin/env python3
"""
Build a customer-specific funds_database.json from a customer fund universe.

Inputs:
  --source     A customer universe file (TSV with columns: Name, ISIN,
               Assetklasse, lfnd. Jahr, 5 Jahre, Risikoklasse (SRI), TER).
  --customer   Customer id (used to pick the output path).

Reads enrichment data from:
  - data/funds/{ISIN}.json    (scraped per-ISIN files from Phase 2)
  - data/customers/general/funds_database.json (master/general profile for
                                                metadata on overlapping ISINs)

Writes:
  data/customers/{customer_id}/funds_database.json   (atomic write)

The output matches the existing schema so decision_engine, validator,
aggregator and the frontend work unchanged. See plan
/home/mrick/.claude/plans/ok-then-on-spicy-parrot.md for the field
resolution chain.

Usage:
  python scripts/build_customer_catalog.py \\
      --customer provinzial_nord \\
      --source notes/Provi-Listing.tsv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from _german_labels import (
    asset_class_from_german,
    category_slug_from_german,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("build_customer_catalog")


# ---------- helpers ----------

NUM_RE = re.compile(r"(-?\d+(?:[\.,]\d+)?)")


def parse_de_number(text: Optional[str]) -> Optional[float]:
    """Parse a German-formatted number (comma decimal, optional % suffix)."""
    if text is None:
        return None
    t = str(text).strip()
    if not t or t in ("–", "-", "—", "n/a", "N/A"):
        return None
    m = NUM_RE.search(t.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def is_etf_from_name(name: str) -> bool:
    if not name:
        return False
    upper = name.upper()
    if "UCITS ETF" in upper or " ETF " in f" {upper} ":
        return True
    return upper.endswith(" ETF") or upper.startswith("ETF ")


# Heuristic provider extraction for funds whose name follows
# "<Provider>-<rest>" or "<Provider> <rest>". Curated list of the prefixes
# we observe in the Provinzial universe. Anything else falls back to the
# scraped fund_name's first token, then "Unknown".
KNOWN_PROVIDERS = [
    ("Deka",                ["Deka-", "Deka ", "Deka:"]),
    ("Berenberg",           ["Berenberg "]),
    ("Lingohr",             ["LINGOHR"]),
    ("Amundi",              ["Amundi "]),
    ("Carmignac",           ["Carmignac "]),
    ("Columbia Threadneedle", ["CT (Lux)", "Threadneedle"]),
    ("Franklin Templeton",  ["Templeton "]),
    ("Flossbach von Storch",["Flossbach"]),
    ("Acatis Investment",   ["ACATIS", "Acatis"]),
    ("ETHENEA Independent Investors", ["Ethna"]),
    ("Fidelity International", ["Fidelity"]),
    ("Pictet Asset Management", ["Pictet"]),
    ("JPMorgan Asset Management", ["JPM "]),
    ("BlackRock",           ["BGF ", "iShares"]),
    ("Vanguard",            ["Vanguard"]),
    ("LBBW Asset Management", ["LBBW"]),
    ("KBI Global Investors (Amundi)", ["KBI "]),
    ("Ökoworld",            ["Ökoworld"]),
    ("Swisscanto (Zürcher Kantonalbank)", ["Swisscanto"]),
    ("Provinzial",          ["Provinzial "]),
    ("Sparkasse / Deka",    ["WeltZins-Invest"]),
    ("Sparkasse UnnaKamen", ["SK "]),
    ("TBF Global Asset Management", ["TBF "]),
    ("DWS",                 ["ARERO"]),
]


def provider_from_name(name: str) -> Optional[str]:
    if not name:
        return None
    for canonical, prefixes in KNOWN_PROVIDERS:
        for p in prefixes:
            if name.startswith(p):
                return canonical
    return None


# ---------- inputs ----------

def read_tsv_universe(path: Path) -> List[Dict[str, Any]]:
    """Parse the customer universe TSV into a list of normalized rows."""
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        if not header:
            raise ValueError(f"Empty TSV: {path}")
        for raw in reader:
            cells = [c.strip() for c in raw]
            if len(cells) < 6 or not cells[1]:
                continue
            ter_raw = cells[6] if len(cells) > 6 else None
            rows.append({
                "name":        cells[0],
                "isin":        cells[1].upper(),
                "asset_class_de": cells[2],
                "ytd_return":  parse_de_number(cells[3]),  # informational only
                "five_y_return": parse_de_number(cells[4]),  # informational only
                "sri":         int(parse_de_number(cells[5])) if cells[5] else None,
                "ter_pct":     parse_de_number(ter_raw),
            })
    return rows


def read_general_profile() -> Dict[str, Dict[str, Any]]:
    path = REPO_ROOT / "data" / "customers" / "general" / "funds_database.json"
    if not path.exists():
        logger.warning("General profile not found at %s — enrichment skipped", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {fund["isin"].upper(): fund for fund in data.get("funds_database", [])}


def read_per_isin(isin: str) -> Optional[Dict[str, Any]]:
    path = REPO_ROOT / "data" / "funds" / f"{isin.upper()}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return None


# ---------- record builder ----------

def _best_horizon(d: Optional[Dict[str, Any]], order: Tuple[str, ...] = ("3y", "5y", "1y")) -> Optional[float]:
    """Return the first non-null value from a {horizon: value} dict, preferring
    longer (more stable) horizons but falling back to shorter ones."""
    if not d:
        return None
    for key in order:
        v = d.get(key)
        if v is not None:
            return v
    return None


def build_record(
    row: Dict[str, Any],
    general_profile: Dict[str, Dict[str, Any]],
    per_isin: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    isin = row["isin"]
    name = row["name"]
    gp   = general_profile.get(isin) or {}
    ts   = per_isin or {}

    asset_class = (
        asset_class_from_german(row["asset_class_de"])
        if row["asset_class_de"]
        else None
    )
    if asset_class == "other":
        # secondary: dominant key from scraped breakdown
        breakdown = (ts.get("asset_class_breakdown") or {})
        if breakdown:
            asset_class = max(breakdown.items(), key=lambda kv: kv[1])[0]
        else:
            asset_class = gp.get("asset_class") or "other"

    yearly_fee = row.get("ter_pct")
    if yearly_fee is None and ts.get("ter") is not None:
        yearly_fee = round(ts["ter"] * 100.0, 4)

    # SRI / risk class: the factsheet "Risikoklasse (SRI)" is authoritative;
    # fall back to the customer listing, then the general profile.
    srri = ts.get("sri")
    if srri is None:
        srri = row.get("sri") if row.get("sri") is not None else gp.get("srri")
    risk_level = gp.get("risk_level")
    if risk_level is None and srri is not None:
        risk_level = max(1, min(5, srri - 1))

    # Risk metrics: prefer the factsheet scrape (best available horizon) over
    # the general-profile guess / yfinance. Sharpe is a plain ratio; volatility
    # and max_drawdown are scraped as fractions and converted to the DB's
    # percent convention (max_drawdown stored as a positive percent).
    ts_rm = ts.get("risk_metrics") or {}
    sharpe = _best_horizon(ts_rm.get("sharpe"))
    if sharpe is None:
        sharpe = gp.get("sharpe_ratio")

    ts_vol = _best_horizon(ts.get("volatility"))
    volatility = round(ts_vol * 100.0, 4) if ts_vol is not None else gp.get("volatility")

    ts_mdd = _best_horizon(ts_rm.get("max_drawdown"))
    max_drawdown = round(abs(ts_mdd) * 100.0, 4) if ts_mdd is not None else gp.get("max_drawdown")

    # Region / theme: factsheet wins. Treat the scrape's defaults ('global' /
    # 'NONE') as "no value" so a curated general-profile value isn't clobbered
    # by a page that simply left the field blank.
    ts_region = ts.get("region")
    region = ts_region if ts_region and ts_region != "global" else gp.get("region", "global")
    ts_theme = ts.get("theme")
    theme = ts_theme if ts_theme and ts_theme != "NONE" else gp.get("theme", "NONE")
    # Normalize real themes to lowercase canonical (the general profile uses an
    # older UPPERCASE convention); keep the 'NONE' sentinel distinct.
    if theme and theme != "NONE":
        theme = theme.lower()

    provider = gp.get("provider") or provider_from_name(name)
    if not provider and ts.get("fund_name"):
        provider = provider_from_name(ts["fund_name"])
    provider = provider or "Unknown"

    categories = gp.get("categories")
    if not categories:
        slug = category_slug_from_german(row["asset_class_de"])
        categories = [slug] if slug and slug != "other" else [asset_class]

    record: Dict[str, Any] = {
        "isin":              isin,
        "ticker":            gp.get("ticker"),
        "name":              name,
        "provider":          provider,
        "url":               gp.get("url"),
        "kiid_url":          gp.get("kiid_url"),
        "asset_class":       asset_class,
        "region":            region,
        "categories":        categories,
        "risk_level":        risk_level,
        "yearly_fee":        yearly_fee,
        "is_etf":            bool(gp.get("is_etf")) or is_etf_from_name(name),
        "esg_label":         gp.get("esg_label", "LOW"),
        "theme":             theme,
        "srri":              srri,
        "sharpe_ratio":      sharpe,
        "volatility":        volatility,
        "max_drawdown":      max_drawdown,
        "esg_article_8":     bool(gp.get("esg_article_8", False)),
        "esg_article_9":     bool(gp.get("esg_article_9", False)),
        "notes":             gp.get("notes") or "Imported from customer universe; enriched from per-ISIN scrape + general profile.",
        "source":            "provinzial_nord_universe",
        "asset_class_breakdown": ts.get("asset_class_breakdown") or gp.get("asset_class_breakdown"),
        "region_breakdown":  gp.get("region_breakdown"),
        "benchmark_id":      gp.get("benchmark_id"),
    }
    return record


def coverage_report(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(records)
    def filled(field: str) -> int:
        return sum(1 for r in records if r.get(field) not in (None, "", "Unknown", []))
    return {
        "total":               n,
        "provider":            f"{filled('provider')}/{n}",
        "region":              f"{filled('region')}/{n}",
        "theme":               f"{sum(1 for r in records if r.get('theme') not in (None, 'NONE'))}/{n}",
        "yearly_fee":          f"{filled('yearly_fee')}/{n}",
        "sharpe_ratio":        f"{filled('sharpe_ratio')}/{n}",
        "asset_class_breakdown": f"{filled('asset_class_breakdown')}/{n}",
        "categories":          f"{filled('categories')}/{n}",
        "esg_article_8":       f"{sum(1 for r in records if r.get('esg_article_8'))}/{n}",
        "is_etf":              f"{sum(1 for r in records if r.get('is_etf'))}/{n}",
    }


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------- main ----------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--customer", required=True, help="Customer profile id (e.g. provinzial_nord)")
    parser.add_argument("--source", required=True, type=Path,
                        help="Path to the customer universe TSV (or future formats)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Override output path (default: data/customers/{customer}/funds_database.json)")
    args = parser.parse_args(argv)

    if not args.source.exists():
        logger.error("Source file not found: %s", args.source)
        return 2

    rows = read_tsv_universe(args.source)
    if not rows:
        logger.error("No usable rows in %s", args.source)
        return 2
    logger.info("Read %d funds from %s", len(rows), args.source)

    general_profile = read_general_profile()
    logger.info("Loaded general profile with %d funds for enrichment", len(general_profile))

    records: List[Dict[str, Any]] = []
    for row in rows:
        ts = read_per_isin(row["isin"])
        record = build_record(row, general_profile, ts)
        records.append(record)

    output_path = args.output or (REPO_ROOT / "data" / "customers" / args.customer / "funds_database.json")
    catalog = {
        "funds_database": records,
        "metadata": {
            "version":            "1.0",
            "schema_version":     2,
            "customer_id":        args.customer,
            "source_file":        str(args.source.relative_to(REPO_ROOT) if args.source.is_absolute() else args.source),
            "built_at":           date.today().isoformat(),
            "last_updated":       date.today().isoformat(),
            "total_funds_shown":  len(records),
            "total_funds_in_db":  len(records),
            "uniform_schema_fields": [
                "isin", "ticker", "name", "provider", "url", "kiid_url",
                "asset_class", "region", "categories", "risk_level",
                "yearly_fee", "is_etf", "esg_article_8", "esg_article_9",
                "esg_label", "theme", "srri", "sharpe_ratio", "volatility",
                "max_drawdown", "notes", "source",
            ],
            "optional_schema_v2_fields": [
                "asset_class_breakdown", "region_breakdown", "benchmark_id",
            ],
            "notes": (
                f"Built by build_customer_catalog.py from {args.source.name}. "
                "Enriched with data/funds/{ISIN}.json (per-ISIN scrape) and "
                "data/customers/general/funds_database.json (general profile)."
            ),
        },
    }

    atomic_write_json(output_path, catalog)
    logger.info("Wrote %s", output_path)

    rep = coverage_report(records)
    logger.info("Coverage report: %s", json.dumps(rep, indent=2))
    print()
    print("=== Field coverage ===")
    for key, val in rep.items():
        print(f"  {key:25s} {val}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
