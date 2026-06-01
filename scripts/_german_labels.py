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


# Provinzial "Region" free-text → our canonical region keys. Matched as
# substrings (case-insensitive) so combined labels like "Nordamerika / USA"
# resolve correctly. Order matters: more specific keywords first.
REGION_FROM_GERMAN = [
    ("nordamerika",    "north_america"),
    ("usa",            "north_america"),
    ("us-",            "north_america"),
    ("kanada",         "north_america"),
    ("schwellenländer", "emerging_markets"),
    ("schwellenlaender", "emerging_markets"),
    ("emerging",       "emerging_markets"),
    # Euro-area funds ("Euroland" / "Eurozone") are European — map to the
    # selectable canonical 'europe' rather than leaving them for the global
    # catch-all (Europe is an explicit region).
    ("euroland",       "europe"),
    ("eurozone",       "europe"),
    ("deutschland",    "germany"),
    ("europa",         "europe"),
    ("asien",          "asia"),
    ("pazifik",        "asia"),
    ("japan",          "asia"),
    ("global",         "global"),
    ("welt",           "global"),
]


def region_from_german(label: str | None) -> str:
    """Map a Provinzial German 'Region' string to a canonical region key.

    Returns 'global' for blank/dash labels and a raw lowercased token for
    unknown labels (so unmapped regions surface rather than silently becoming
    'global').
    """
    if not label:
        return "global"
    s = label.strip().lower()
    if s in ("", "–", "-", "—", "n/a"):
        return "global"
    for keyword, key in REGION_FROM_GERMAN:
        if keyword in s:
            return key
    return s.replace(" ", "_")


# Provinzial "Thema" free-text → our canonical theme keys (kept verbatim with
# the DB tag vocabulary: commodities, defense, ...). Substring match.
THEME_FROM_GERMAN = [
    ("dividend",       "dividends"),
    ("rohstoff",       "commodities"),
    ("gesundheit",     "healthcare"),
    ("pharma",         "healthcare"),
    ("technologie",    "technology"),
    ("robotik",        "ai_robotics"),
    ("künstliche intelligenz", "ai_robotics"),
    ("kuenstliche intelligenz", "ai_robotics"),
    (" ki ",           "ai_robotics"),
    ("nachhaltig",     "sustainability"),
    ("klima",          "sustainability"),
    ("esg",            "sustainability"),
    ("ökolog",         "sustainability"),
    ("oekolog",        "sustainability"),
    ("umwelt",         "sustainability"),
    ("infrastruktur",  "infrastructure"),
    ("wasser",         "water"),
    ("sicherheit",     "defense"),
    ("verteidigung",   "defense"),
    ("rüstung",        "defense"),
    ("ruestung",       "defense"),
    ("energie",        "energy"),
    ("megatrend",      "megatrends"),
]


def theme_from_german(label: str | None) -> str:
    """Map a Provinzial German 'Thema' string to a canonical theme key.

    Returns 'NONE' for blank/dash labels (page-faithful — no guessing) and a
    raw uppercased token for unknown non-blank labels.
    """
    if not label:
        return "NONE"
    s = label.strip().lower()
    if s in ("", "–", "-", "—", "n/a", "keine", "kein thema"):
        return "NONE"
    padded = f" {s} "
    for keyword, key in THEME_FROM_GERMAN:
        if keyword in padded:
            return key
    return s.replace(" ", "_").upper()


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
