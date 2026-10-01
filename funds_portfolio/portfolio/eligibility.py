"""Shared preference-eligibility predicates — single source of truth.

Extracted from ``decision_engine.py`` (same pattern as ``risk_bands.py``)
so the dialog feasibility advisor evaluates "would this fund survive the
ESG / ETF preference filters?" with the exact semantics the engine's hard
filters apply. The engine delegates here; re-declaring these rules anywhere
else is a bug.

Filter semantics (mirrors the engine pipeline):
  * ESG: only ``ART_8_9_ONLY`` excludes funds — a fund is eligible iff its
    ``esg_label`` is SFDR Article 8 or 9. ``NONE`` and ``PREFER_ESG`` never
    exclude (PREFER_ESG only boosts).
  * ETF: only ``etf_only`` excludes funds — a fund is eligible iff
    ``is_etf`` is true. ``no_preference`` and ``prefer_etf`` never exclude.
  * Product context (layer-0): only a supplied product excludes funds — a
    fund is eligible iff the canonical product key is in its ``valid_for``
    list. No product context (None/empty) never excludes (backward
    compatible). Imported per strict rule: only a plain ``ja`` in the
    compass CSV columns L–T is valid; conditional annotations
    (``ja (SW)``, ``Ablaufm. T93``, ``Einstiegsm.`` …) are NOT valid.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Funds considered "sustainable" for boosting/filtering: SFDR Article 8 & 9.
ESG_SUSTAINABLE_LABELS = ("SFDR_ARTICLE_8", "SFDR_ARTICLE_9")

# Canonical esg_preference answers that trigger hard filtering.
ESG_ONLY_VALUE = "ART_8_9_ONLY"
# Canonical etf_preference answers that trigger hard filtering.
ETF_ONLY_VALUE = "etf_only"


def is_esg_fund(fund: Dict[str, Any]) -> bool:
    """True if the fund satisfies the SFDR Article 8/9 requirement."""
    return str(fund.get("esg_label") or "").upper() in ESG_SUSTAINABLE_LABELS


def normalise_esg_preference(pref: Any) -> str:
    """Map any stored value to the canonical set NONE | PREFER_ESG | ART_8_9_ONLY.

    Tolerates legacy answers (no_requirement/esg_basic/esg_enhanced) from
    portfolios created before the ESG refactor. Unknown -> NONE.
    """
    p = str(pref or "").strip().upper()
    legacy = {
        "NO_REQUIREMENT": "NONE",
        "ESG_BASIC": "ART_8_9_ONLY",
        "ESG_ENHANCED": "ART_8_9_ONLY",
    }
    p = legacy.get(p, p)
    return p if p in ("NONE", "PREFER_ESG", ESG_ONLY_VALUE) else "NONE"


def esg_eligible(fund: Dict[str, Any], esg_preference: Any) -> bool:
    """Fund eligibility under the ESG preference (non-filtering → True)."""
    if esg_preference != ESG_ONLY_VALUE:
        return True
    return is_esg_fund(fund)


def etf_eligible(fund: Dict[str, Any], etf_preference: Any) -> bool:
    """Fund eligibility under the ETF preference (non-filtering → True)."""
    if etf_preference != ETF_ONLY_VALUE:
        return True
    return bool(fund.get("is_etf"))


def preference_eligible(
    fund: Dict[str, Any], esg_preference: Any = None, etf_preference: Any = None
) -> bool:
    """Combined hard-filter eligibility (ESG ∧ ETF)."""
    return esg_eligible(fund, esg_preference) and etf_eligible(fund, etf_preference)


def filter_by_preferences(
    funds: List[Dict[str, Any]],
    esg_preference: Any = None,
    etf_preference: Any = None,
) -> List[Dict[str, Any]]:
    """All funds surviving both hard preference filters."""
    return [f for f in funds if preference_eligible(f, esg_preference, etf_preference)]


# ---------------------------------------------------------------------------
# Product context (layer-0) — single source of truth
#
# The insurance-product validity matrix comes from the Provinzial funds
# compass CSV (columns L–T). Three column headlines are compound families;
# each member becomes an individual canonical key sharing the column's
# validity. Import rule (strict, user decision 2026-10-01): a product is
# only in a fund's ``valid_for`` when the raw cell is exactly ``ja``
# (whitespace/case-normalised) — every other annotation is not valid.
# ---------------------------------------------------------------------------

# (csv column headline, canonical keys) — ordered by CSV column L..T
# (0-based indices 11..19). Column order doubles as the import mapping.
PRODUCT_COLUMNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("STANDARDDEPOT", ("standarddepot",)),
    ("AVI", ("avi",)),
    ("AVG80", ("avg80",)),
    ("AVG100", ("avg100",)),
    (
        "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
        ("garantrentevario", "flexgarant", "firmengarantrente", "firmenflexgarant"),
    ),
    (
        "BASISGARANTRENTE / BASISFLEXGARANT",
        ("basisgarantrente", "basisflexgarant"),
    ),
    (
        "FONDSRENTEVARIO / STARTERKIDS",
        ("fondsrentevario", "starterkids"),
    ),
    ("1LF", ("1lf",)),
    ("1LTF", ("1ltf",)),
)

# Canonical product catalog: key → display label + defining CSV column.
PRODUCTS: Dict[str, Dict[str, Any]] = {
    "standarddepot": {
        "label": "StandardDepot",
        "column": "STANDARDDEPOT",
    },
    "avi": {"label": "AVI", "column": "AVI"},
    "avg80": {"label": "AVG80", "column": "AVG80"},
    "avg100": {"label": "AVG100", "column": "AVG100"},
    "garantrentevario": {
        "label": "GarantRenteVario",
        "column": "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
    },
    "flexgarant": {
        "label": "FlexGarant",
        "column": "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
    },
    "firmengarantrente": {
        "label": "FirmenGarantRente",
        "column": "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
    },
    "firmenflexgarant": {
        "label": "FirmenFlexGarant",
        "column": "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
    },
    "basisgarantrente": {
        "label": "BasisGarantRente",
        "column": "BASISGARANTRENTE / BASISFLEXGARANT",
    },
    "basisflexgarant": {
        "label": "BasisFlexGarant",
        "column": "BASISGARANTRENTE / BASISFLEXGARANT",
    },
    "fondsrentevario": {
        "label": "FondsRenteVario",
        "column": "FONDSRENTEVARIO / STARTERKIDS",
    },
    "starterkids": {
        "label": "StarterKids",
        "column": "FONDSRENTEVARIO / STARTERKIDS",
    },
    "1lf": {"label": "1LF", "column": "1LF"},
    "1ltf": {"label": "1LTF", "column": "1LTF"},
}

# Input aliases (lowercased) accepted by normalise_product(): canonical
# keys, display labels and full compound headlines.
_PRODUCT_ALIASES: Dict[str, str] = {}
for _key, _meta in PRODUCTS.items():
    _PRODUCT_ALIASES[_key.lower()] = _key
    _PRODUCT_ALIASES[str(_meta["label"]).lower()] = _key
for _headline, _keys in PRODUCT_COLUMNS:
    _PRODUCT_ALIASES[" ".join(_headline.lower().split())] = _keys[0]


def normalise_product(value: Any) -> Optional[str]:
    """Map any supplied value to a canonical product key.

    Accepts canonical keys, display labels and raw CSV headlines
    (case-insensitive, whitespace-collapsed). Returns None when absent —
    the caller treats None as "no product context" (filter off).
    """
    if value is None:
        return None
    v = " ".join(str(value).strip().lower().split())
    if not v:
        return None
    if v in PRODUCTS:
        return v
    return _PRODUCT_ALIASES.get(v)


def product_eligible(fund: Dict[str, Any], product: Any = None) -> bool:
    """Fund eligibility under the product context (no context → True).

    A fund is eligible iff the canonical product key appears in its
    ``valid_for`` list. Funds without ``valid_for`` (legacy entries not yet
    re-synced from the compass CSV) are dropped whenever a product context
    is set — full-sync semantics: the CSV is the master list.
    """
    canonical = normalise_product(product)
    if canonical is None:
        return True
    return canonical in (fund.get("valid_for") or [])


def filter_by_product(
    funds: List[Dict[str, Any]], product: Any = None
) -> List[Dict[str, Any]]:
    """All funds surviving the layer-0 product-context filter."""
    return [f for f in funds if product_eligible(f, product)]
