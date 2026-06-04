#!/usr/bin/env python3
"""Backfill volatility / max_drawdown / sharpe_ratio on the general catalog.

The decision engine now requires every eligible fund to carry volatility,
max_drawdown and sharpe_ratio. The general customer catalog predates that
requirement, so this script fills the gaps:

  1. Real values copied from the root funds_database.json for overlapping ISINs.
  2. SRRI-derived proxies (the same maps the engine uses) for the rest.

Sharpe has no SRRI proxy in the engine, so missing sharpe falls back to a
modest neutral placeholder. Idempotent: existing non-null values are kept.

Usage:
  python scripts/backfill_general_metrics.py [--write]
"""

from __future__ import annotations

import argparse
import json
import os

from funds_portfolio.portfolio.decision_engine import SRRI_MDD_PROXY, SRRI_VOL_PROXY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_CATALOG = os.path.join(ROOT, "funds_database.json")
GENERAL_CATALOG = os.path.join(ROOT, "data", "customers", "general", "funds_database.json")

SHARPE_PROXY = 0.5  # neutral placeholder when neither real value nor proxy exists


def _srri(fund: dict) -> int:
    srri = fund.get("srri") or fund.get("risk_level") or 4
    return max(1, min(7, int(srri)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="persist changes (otherwise dry-run)")
    args = ap.parse_args()

    with open(ROOT_CATALOG, encoding="utf-8") as f:
        root_funds = json.load(f)["funds_database"]
    root_by_isin = {f["isin"]: f for f in root_funds}

    with open(GENERAL_CATALOG, encoding="utf-8") as f:
        general = json.load(f)
    funds = general["funds_database"]

    filled = {"real": 0, "proxy": 0}
    for fund in funds:
        src = root_by_isin.get(fund["isin"], {})
        used_real = False
        for field, proxy_map in (
            ("volatility", SRRI_VOL_PROXY),
            ("max_drawdown", SRRI_MDD_PROXY),
        ):
            if fund.get(field) is not None:
                continue
            if src.get(field) is not None:
                fund[field] = src[field]
                used_real = True
            else:
                fund[field] = proxy_map[_srri(fund)]
        if not fund.get("sharpe_ratio"):
            if src.get("sharpe_ratio"):
                fund["sharpe_ratio"] = src["sharpe_ratio"]
                used_real = True
            else:
                fund["sharpe_ratio"] = SHARPE_PROXY
        filled["real" if used_real else "proxy"] += 1

    print(f"funds={len(funds)} touched_with_real={filled['real']} proxy_only={filled['proxy']}")

    if args.write:
        with open(GENERAL_CATALOG, "w", encoding="utf-8") as f:
            json.dump(general, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {GENERAL_CATALOG}")
    else:
        print("dry-run; pass --write to persist")


if __name__ == "__main__":
    main()
