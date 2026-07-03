"""Shared preference-satisfaction scoring.

Single source of truth for "how many of the user's stated preferences does the
portfolio fulfil?" — used by:

* the decision engine (persisted to ``portfolio_metrics`` + ``decision_trace``);
* the eval harness metrics (so the engine and the eval never disagree);
* the GUI summary / preferences tabs.

Counting rule (per the FundsPortfolio tuning spec):
  - **Denominator (dynamic, 2..7)** = 1 (risk_approach) + 1 (esg_preference) +
    1 (etf_preference) + |preferred_regions| (0..2) + |preferred_themes| (0..2).
    The three single-selects are always present; the multi-selects contribute
    one slot per chip the user actually picked.
  - **Fulfilled** = the trait is satisfied by *any* selected fund
    (set-membership across the portfolio; no double-counting — each trait is
    met-or-not, counted exactly once):
      * risk  : always fulfilled (the engine guarantees the risk band; false
                only when the trace shows a relaxation / fallback was used);
      * esg   : NONE = always fulfilled (no preference); PREFER_ESG = any
                SFDR Article 8/9 fund; ART_8_9_ONLY = *every* fund is Art 8/9;
      * etf   : no_preference = always; prefer_etf = any ETF; etf_only = no
                active-fund fallback used;
      * region: any fund whose ``region`` equals the requested value;
      * theme : any fund whose ``theme`` equals the requested value.

The trait predicates mirror ``DecisionEngine``'s own logic so there is no
"second truth" — see the engine's explanation builder for the same checks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

_ESG_SUSTAINABLE_LABELS = ("SFDR_ARTICLE_8", "SFDR_ARTICLE_9")


def _is_esg_fund(fund: Dict[str, Any]) -> bool:
    return str(fund.get("esg_label") or "").upper() in _ESG_SUSTAINABLE_LABELS


def preference_satisfaction(
    user_answers: Dict[str, Any],
    recommendations: Sequence[Dict[str, Any]],
    *,
    relaxations: Sequence[Dict[str, Any]] = (),
    used_fallback_risk: bool = False,
) -> Dict[str, Any]:
    """Compute the preference-satisfaction breakdown for one portfolio.

    Args:
        user_answers: the questionnaire answers fed to the engine.
        recommendations: the engine's selected funds (``result["recommendations"]``).
        relaxations: ``decision_trace["relaxations"]`` (used for the risk item).
        used_fallback_risk: ``decision_trace["used_fallback_risk"]``.

    Returns:
        ``{fulfilled, total, display, per_item}`` where ``per_item`` is a list
        of ``{dimension, value, fulfilled}`` in the canonical order
        risk, esg, etf, then regions, then themes.
    """
    recs = list(recommendations)
    per_item: List[Dict[str, Any]] = []

    # --- risk_approach (always one slot) ---
    risk_fulfilled = not relaxations and not used_fallback_risk
    per_item.append(
        {
            "dimension": "risk_approach",
            "value": user_answers.get("risk_approach"),
            "fulfilled": bool(risk_fulfilled),
        }
    )

    # --- esg_preference (always one slot) ---
    esg_pref = str(user_answers.get("esg_preference") or "NONE").upper()
    if esg_pref == "NONE":
        esg_fulfilled = True
    elif esg_pref == "ART_8_9_ONLY":
        esg_fulfilled = bool(recs) and all(_is_esg_fund(r) for r in recs)
    else:  # PREFER_ESG
        esg_fulfilled = any(_is_esg_fund(r) for r in recs)
    per_item.append(
        {"dimension": "esg_preference", "value": esg_pref, "fulfilled": esg_fulfilled}
    )

    # --- etf_preference (always one slot) ---
    etf_pref = str(user_answers.get("etf_preference") or "no_preference")
    if etf_pref == "no_preference":
        etf_fulfilled = True
    elif etf_pref == "etf_only":
        # Fulfilled only if the engine didn't backfill active funds.
        etf_fulfilled = not any(r.get("etf_not_available") for r in recs)
    else:  # prefer_etf
        etf_fulfilled = any(r.get("is_etf") for r in recs)
    per_item.append(
        {"dimension": "etf_preference", "value": etf_pref, "fulfilled": etf_fulfilled}
    )

    # --- preferred_regions (one slot per requested chip) ---
    for region in (user_answers.get("preferred_regions") or []):
        region_l = str(region).lower()
        fulfilled = any(str(r.get("region") or "").lower() == region_l for r in recs)
        per_item.append(
            {"dimension": "preferred_regions", "value": region, "fulfilled": fulfilled}
        )

    # --- preferred_themes (one slot per requested chip) ---
    for theme in (user_answers.get("preferred_themes") or []):
        if str(theme).lower() == "none":
            continue  # "none" means "no theme preference" — not a real request
        theme_l = str(theme).lower()
        fulfilled = any(str(r.get("theme") or "").lower() == theme_l for r in recs)
        per_item.append(
            {"dimension": "preferred_themes", "value": theme, "fulfilled": fulfilled}
        )

    total = len(per_item)
    fulfilled = sum(1 for item in per_item if item["fulfilled"])
    return {
        "fulfilled": fulfilled,
        "total": total,
        "display": f"{fulfilled}/{total}",
        "per_item": per_item,
    }
