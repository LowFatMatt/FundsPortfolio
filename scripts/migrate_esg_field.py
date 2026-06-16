#!/usr/bin/env python3
"""One-shot, idempotent migration of the ESG data model.

Collapses the three ESG fields (esg_label, esg_article_8, esg_article_9) down to
a single esg_label with the reduced value set:

    null | "SFDR_ARTICLE_6" | "SFDR_ARTICLE_8" | "SFDR_ARTICLE_9"

Rules:
  - Article 9 (label SFDR_ARTICLE_9/HIGH or esg_article_9 True)  -> SFDR_ARTICLE_9
  - Article 8 (label SFDR_ARTICLE_8/MEDIUM or esg_article_8 True) -> SFDR_ARTICLE_8
  - everything else (LOW / unknown)                              -> None
  - esg_article_8 / esg_article_9 keys are removed.

Re-running on an already-migrated file is a no-op.

Usage:  python scripts/migrate_esg_field.py [path-to-funds_database.json]
"""

import json
import sys


def migrate_label(fund: dict) -> object:
    label = str(fund.get("esg_label") or "").upper()
    if fund.get("esg_article_9") is True or label in ("SFDR_ARTICLE_9", "HIGH"):
        return "SFDR_ARTICLE_9"
    if fund.get("esg_article_8") is True or label in ("SFDR_ARTICLE_8", "MEDIUM"):
        return "SFDR_ARTICLE_8"
    # LOW / null / unknown -> not classified
    return None


def main(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    funds = data["funds_database"] if isinstance(data, dict) else data

    changed = 0
    for fund in funds:
        new_label = migrate_label(fund)
        if fund.get("esg_label") != new_label:
            changed += 1
        fund["esg_label"] = new_label
        fund.pop("esg_article_8", None)
        fund.pop("esg_article_9", None)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    print(f"migrated {len(funds)} funds in {path} (labels changed: {changed})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "funds_database.json")
