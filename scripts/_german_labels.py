"""
Shared taxonomy helpers for German fund metadata.

Used by both the factsheetslive scraper and the customer-catalog builder so
the asset_class mapping stays consistent. Keeping it as a tiny module
avoids a cross-script import cycle and makes the mappings explicit.
"""

from __future__ import annotations

from typing import Dict


# Provinzial "Fondsart" (asset class) labels → our canonical schema keys.
ASSET_CLASS_FROM_GERMAN: Dict[str, str] = {
    "aktienfonds":                "equity",
    "mischfonds":                 "mixed",
    "renten/geldmarktfonds":      "bond",
    "immobilienfonds":            "real_estate",
    "wertsicherungsfonds":        "mixed",
    "vermögensverwaltende fonds": "mixed",
    "bankspezifische fonds":      "mixed",
}


# Category slug per German label — used to populate the catalog's `categories`
# list when no other source is available. Keeps the existing slug vocabulary
# (balanced, global_bonds, …) so downstream filters keep working.
CATEGORY_SLUG_FROM_GERMAN: Dict[str, str] = {
    "aktienfonds":                "equity",
    "mischfonds":                 "balanced",
    "renten/geldmarktfonds":      "fixed_income",
    "immobilienfonds":            "real_estate",
    "wertsicherungsfonds":        "capital_protection",
    "vermögensverwaltende fonds": "multi_asset",
    "bankspezifische fonds":      "bank_specific",
}


def asset_class_from_german(label: str | None) -> str:
    """Map a Provinzial German Fondsart string to a canonical asset_class key."""
    if not label:
        return "other"
    return ASSET_CLASS_FROM_GERMAN.get(label.strip().lower(), "other")


def category_slug_from_german(label: str | None) -> str:
    """Map a German Fondsart label to a single category slug for `categories`."""
    if not label:
        return "other"
    return CATEGORY_SLUG_FROM_GERMAN.get(label.strip().lower(), "other")


def canonical_asset_class_from_breakdown_key(key: str) -> str:
    """
    Map a free-form breakdown label (Aktien, Rohstoffe, ...) to a canonical key.
    Used by the scraper when reading the page's allocation-bar rows.
    """
    s = (key or "").lower()
    if "aktie" in s:                                      return "equity"
    if "renten" in s or "anleih" in s or "bond" in s:     return "bond"
    if "immo" in s or "real estate" in s:                 return "real_estate"
    if "rohstoff" in s or "commodit" in s or "gold" in s: return "commodities"
    if "geldmarkt" in s or "cash" in s or "kasse" in s:   return "cash"
    if "deriv" in s or "option" in s:                     return "derivatives"
    return "other"
