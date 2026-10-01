"""Import product-validity columns (L-T) from the funds compass CSV.

Reads the Provinzial "Liste 4 FundsCompass" CSV and writes a ``valid_for``
list (canonical insurance-product keys) onto every fund entry in
``funds_database.json``. The CSV is treated as the master list:

* funds matched by ISIN (or, as fallback, by name) get ``valid_for`` set;
* CSV-only funds are appended as minimal stub entries (inert for the
  engine until metrics are enriched);
* funds in the database but absent from the CSV are reported for review
  (and optionally removed with ``--remove-absent``).

Strict boolean rule (decision 2026-10-01): a product key is only included
when the raw cell is exactly ``ja`` (whitespace/case-normalised). Every
other annotation — ``nein``, ``ja (SW)``, ``ja (NW)``, ``Ablaufm. T93``,
``Einstiegsm.``, ``nein (alte WSF)`` — means NOT valid, but all
annotations are listed in the report so nothing disappears silently.

The column mapping and canonical keys come from
``funds_portfolio.portfolio.eligibility`` (single source of truth shared
with the layer-0 engine filter).

Usage:
    python scripts/import_product_validity.py \\
        funds_database.json notes/20260928-List4FundsCompass.csv \\
        [--dry-run] [--remove-absent] [--report-file report.txt]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Allow running from a checkout without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from funds_portfolio.portfolio.eligibility import PRODUCT_COLUMNS  # noqa: E402

# CSV column indices (0-based) — the headline row is too dirty for
# name-based access (duplicate "Region" columns, stray whitespace).
COL_NAME = 3
COL_ISIN = 4
COL_COST = 5
COL_ESG = 8
COL_KVG = 10
COL_VALIDITY_START = 11  # column "L" == first validity column
COL_TICKER = 25

ESG_LABEL_MAP = {
    "art. 8": "SFDR_ARTICLE_8",
    "art. 9": "SFDR_ARTICLE_9",
    "art. 6": None,
}

SOURCE_TAG = "csv_20260928"


def _norm_isin(raw: Optional[str]) -> Optional[str]:
    """`(LU0703710904)` / `LU0703710904 ` → `LU0703710904`; None when empty."""
    if raw is None:
        return None
    v = raw.strip().strip("()").strip().upper()
    return v or None


def _norm_name(raw: Optional[str]) -> str:
    return " ".join(str(raw or "").split()).casefold()


def _parse_fee(raw: Optional[str]) -> Optional[float]:
    """`1,00%` → 1.0; empty/invalid → None."""
    if not raw or not raw.strip():
        return None
    v = raw.strip().rstrip("%").replace(",", ".").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _is_plain_ja(raw: Optional[str]) -> bool:
    return str(raw or "").strip().casefold() == "ja"


def _row_validity(row: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Canonical product keys + excluded annotations for one CSV row.

    Returns (valid_for, annotations) where annotations is a list of
    (column headline, raw value) for every non-empty cell that is neither
    a plain ``ja`` nor a plain ``nein``.
    """
    valid: List[str] = []
    annotations: List[Tuple[str, str]] = []
    for offset, (headline, keys) in enumerate(PRODUCT_COLUMNS):
        cell = (row[COL_VALIDITY_START + offset] or "").strip() if len(row) > COL_VALIDITY_START + offset else ""
        if _is_plain_ja(cell):
            valid.extend(keys)
        elif cell and cell.casefold() != "nein":
            annotations.append((headline, cell))
    return valid, annotations


def _build_stub(row: List[str], isin: Optional[str], valid_for: List[str]) -> Dict[str, Any]:
    esg_raw = (row[COL_ESG] or "").strip() if len(row) > COL_ESG else ""
    stub: Dict[str, Any] = {
        "isin": isin,
        "ticker": ((row[COL_TICKER] or "").strip() if len(row) > COL_TICKER and row[COL_TICKER] else None) or None,
        "name": (row[COL_NAME] or "").strip() if len(row) > COL_NAME else None,
        "provider": (row[COL_KVG] or "").strip() if len(row) > COL_KVG else None,
        "asset_class": None,
        "region": None,
        "categories": [],
        "risk_level": None,
        "yearly_fee": _parse_fee(row[COL_COST] if len(row) > COL_COST else None),
        "is_etf": str(row[0] or "").startswith("Indexfonds-ETF") if row else False,
        "esg_label": ESG_LABEL_MAP.get(esg_raw.casefold()),
        "theme": "NONE",
        "valid_for": valid_for,
        "notes": "Stub from compass CSV import — risk metrics pending enrichment.",
        "source": SOURCE_TAG,
        "asset_class_breakdown": None,
        "region_breakdown": None,
        "benchmark_id": None,
    }
    return stub


def import_product_validity(
    db_path: str,
    csv_path: str,
    dry_run: bool = False,
    remove_absent: bool = False,
    report_file: Optional[str] = None,
) -> int:
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    funds: List[Dict[str, Any]] = data.get("funds_database", [])

    isin_index = {f.get("isin"): f for f in funds if f.get("isin")}
    name_index: Dict[str, Dict[str, Any]] = {}
    for f in funds:
        if f.get("name"):
            name_index.setdefault(_norm_name(f["name"]), f)

    matched_isin: List[str] = []
    matched_name: List[Tuple[str, str, str]] = []  # (name, csv_isin, db_isin)
    stubs: List[Dict[str, Any]] = []
    annotations_seen: List[Tuple[str, str, str]] = []  # (fund, headline, raw)
    nowh: List[str] = []
    touched = set()  # identities (id()) of funds that the CSV covers

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = [r for r in reader if any((c or "").strip() for c in r)]
    rows = rows[1:]  # drop headline

    for row in rows:
        name = (row[COL_NAME] or "").strip() if len(row) > COL_NAME else ""
        csv_isin = _norm_isin(row[COL_ISIN]) if len(row) > COL_ISIN else None
        valid, annotations = _row_validity(row)

        fund = None
        if csv_isin and csv_isin in isin_index:
            fund = isin_index[csv_isin]
            matched_isin.append(csv_isin)
        elif name and _norm_name(name) in name_index:
            fund = name_index[_norm_name(name)]
            matched_name.append((name, csv_isin or "—", fund.get("isin") or "—"))

        if fund is not None:
            fund["valid_for"] = valid
            touched.add(id(fund))
            if not valid:
                nowh.append(name or csv_isin or "?")
        else:
            stubs.append(_build_stub(row, csv_isin, valid))

        for headline, raw in annotations:
            annotations_seen.append((name or csv_isin or "?", headline, raw))

    # Funds in the DB but not covered by any CSV row (full-sync check).
    absent = [f for f in funds if id(f) not in touched]
    if remove_absent and absent:
        funds = [f for f in funds if id(f) in touched]

    # Append stubs (CSV-only funds) — deduped against existing ISINs/names.
    existing_isins = {f.get("isin") for f in funds if f.get("isin")}
    existing_names = {_norm_name(f.get("name")) for f in funds if f.get("name")}
    added = []
    for stub in stubs:
        if stub.get("isin") and stub["isin"] in existing_isins:
            continue
        if stub.get("name") and _norm_name(stub["name"]) in existing_names:
            continue
        funds.append(stub)
        added.append(stub)

    # ------------------------------------------------------------------ report
    lines: List[str] = []
    lines.append(f"Product-validity import — {csv_path} → {db_path}")
    lines.append(f"  CSV rows: {len(rows)}")
    lines.append(f"  Matched by ISIN: {len(matched_isin)}")
    lines.append(f"  Matched by name (ISIN remap candidates): {len(matched_name)}")
    for name, csv_isin, db_isin in matched_name:
        lines.append(f"    - {name}: CSV ISIN {csv_isin} vs DB ISIN {db_isin} (DB ISIN kept)")
    lines.append(f"  Stubs added (CSV-only funds): {len(added)}")
    for s in added:
        lines.append(f"    + {s.get('name')} ({s.get('isin') or 'no ISIN'})")
    lines.append(f"  DB funds absent from CSV (review{' — REMOVED' if remove_absent else ''}): {len(absent)}")
    for f in absent:
        lines.append(f"    - {f.get('name')} ({f.get('isin')})")
    lines.append(f"  Funds valid for NO product (valid_for == []): {len(nowh)}")
    for n in nowh:
        lines.append(f"    ! {n}")
    lines.append(f"  Conditional annotations excluded (strict rule): {len(annotations_seen)}")
    for fund, headline, raw in annotations_seen:
        lines.append(f"    * {fund} :: {headline} :: {raw!r}")

    report = "\n".join(lines)
    print(report)

    if report_file:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report + "\n")

    if dry_run:
        print("\n[dry-run] No changes written.")
        return 0

    data["funds_database"] = funds
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nWritten {db_path}: {len(funds)} funds ({len(added)} stubs added).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db_path", help="Path to funds_database.json")
    parser.add_argument("csv_path", help="Path to the funds compass CSV")
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    parser.add_argument(
        "--remove-absent",
        action="store_true",
        help="Remove DB funds absent from the CSV (default: report only)",
    )
    parser.add_argument("--report-file", default=None, help="Also write the report to this path")
    args = parser.parse_args()
    return import_product_validity(
        args.db_path,
        args.csv_path,
        dry_run=args.dry_run,
        remove_absent=args.remove_absent,
        report_file=args.report_file,
    )


if __name__ == "__main__":
    sys.exit(main())
