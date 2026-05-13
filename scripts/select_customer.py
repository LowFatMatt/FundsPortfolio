#!/usr/bin/env python3
"""
Activate a customer fund catalog as the runtime default.

Copies data/customers/{customer_id}/funds_database.json over the repo-root
funds_database.json so existing code paths (tests, Docker mount, default
provider config) pick it up without changes. Records the active id in
data/customers/.active for diagnostics.

Usage:
  python scripts/select_customer.py provinzial_nord
  python scripts/select_customer.py --list
  python scripts/select_customer.py --current
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOMERS_DIR = REPO_ROOT / "data" / "customers"
ACTIVE_MARKER = CUSTOMERS_DIR / ".active"
ROOT_CATALOG = REPO_ROOT / "funds_database.json"


def list_customers() -> list[str]:
    if not CUSTOMERS_DIR.exists():
        return []
    return sorted(
        p.name for p in CUSTOMERS_DIR.iterdir()
        if p.is_dir() and (p / "funds_database.json").exists()
    )


def current_customer() -> str | None:
    if ACTIVE_MARKER.exists():
        return ACTIVE_MARKER.read_text(encoding="utf-8").strip() or None
    # Best-effort: read the metadata of the root catalog
    if ROOT_CATALOG.exists():
        try:
            with open(ROOT_CATALOG, "r", encoding="utf-8") as f:
                return (json.load(f).get("metadata") or {}).get("customer_id")
        except (OSError, json.JSONDecodeError):
            return None
    return None


def activate(customer_id: str) -> int:
    src = CUSTOMERS_DIR / customer_id / "funds_database.json"
    if not src.exists():
        print(f"error: no catalog at {src}", file=sys.stderr)
        print("Available customers:", ", ".join(list_customers()) or "(none)", file=sys.stderr)
        return 2
    # Atomic-ish: copy to .tmp then replace
    tmp = ROOT_CATALOG.with_suffix(ROOT_CATALOG.suffix + ".tmp")
    shutil.copyfile(src, tmp)
    tmp.replace(ROOT_CATALOG)
    ACTIVE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_MARKER.write_text(customer_id + "\n", encoding="utf-8")
    print(f"Activated customer profile: {customer_id}")
    print(f"  source: {src.relative_to(REPO_ROOT)}")
    print(f"  active: {ROOT_CATALOG.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("customer", nargs="?", help="Customer id to activate")
    parser.add_argument("--list", action="store_true", help="List available customer profiles")
    parser.add_argument("--current", action="store_true", help="Print the currently active customer")
    args = parser.parse_args(argv)

    if args.list:
        customers = list_customers()
        if not customers:
            print("(no customer profiles found in data/customers/)")
            return 0
        active = current_customer()
        for c in customers:
            marker = " *" if c == active else ""
            print(f"  {c}{marker}")
        return 0

    if args.current:
        cur = current_customer()
        print(cur or "(unknown)")
        return 0

    if not args.customer:
        parser.print_help()
        return 1
    return activate(args.customer)


if __name__ == "__main__":
    sys.exit(main())
