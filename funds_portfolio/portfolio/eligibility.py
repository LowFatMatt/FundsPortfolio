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
"""

from __future__ import annotations

from typing import Any, Dict, List

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
    return esg_eligible(fund, esg_preference) and etf_eligible(
        fund, etf_preference
    )


def filter_by_preferences(
    funds: List[Dict[str, Any]],
    esg_preference: Any = None,
    etf_preference: Any = None,
) -> List[Dict[str, Any]]:
    """All funds surviving both hard preference filters."""
    return [
        f
        for f in funds
        if preference_eligible(f, esg_preference, etf_preference)
    ]
