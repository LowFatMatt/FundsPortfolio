"""Shared risk-band definitions — the single source of truth.

The bands were extracted from ``decision_engine.py`` so the dialog layer
(feasibility advisor, questionnaire loader) can evaluate "would this fund be
selectable for this risk profile?" without importing the whole engine or —
worse — re-declaring the band values. The engine delegates to this module;

Used by:
  * ``DecisionEngine._risk_band_for_profile`` / ``_fund_in_risk_band`` (hard
    filter — the compliance backstop),
  * ``funds_portfolio/dialog/feasibility.py`` (dialog answer-space shaping).
"""

from __future__ import annotations

from typing import Any, Dict, List

# NOTE: These values are subject ot change based on tests with the current universe.
# The values below are the ones used in the v4 logic, which is the current logic used in the app.
RISK_BANDS: Dict[str, Dict[str, Any]] = {
    "DEFENSIVE": {
        "srri_min": 1,
        "srri_max": 3,
        "vol_max": 8.0,
        "vol_min": None,
        "mdd_max": 15.0,
    },
    "BALANCED": { # risk band changes after tests with v4 logic
        "srri_min": 2,
        "srri_max": 4,
        "vol_min": 5.0,
        "vol_max": 15.0,
        "mdd_max": 25.0,
    },
    "OPPORTUNITY": {
        "srri_min": 4,
        "srri_max": 7,
        "vol_max": None,
        "vol_min": 10.0,
        "mdd_max": 50.0,
    },
}

# v4 allocation policy: maximum total share of the portfolio that satellites
# may receive (percentage). OPPORTUNITY is deliberately more generous (40 %)
# so that 3 satellites do not force equal 10 % floor allocations; the other
# profiles keep the original 30 %.
SATELLITE_TOTAL_CAPS: Dict[str, float] = {
    "DEFENSIVE": 30.0,
    "BALANCED": 30.0,
    "OPPORTUNITY": 40.0,
}

# v4.1 allocation policy: fixed defensive-anchor budget per profile (% of the
# portfolio). Pass 0 (see ``decision_engine._select_defensive_anchor``)
# reserves exactly this share for one top-scored DEFENSIVE-band bond fund
# before the coverage/quality passes run — the deliberate defensive bias that
# keeps BALANCED portfolios inside their equity corridor. DEFENSIVE needs no
# anchor (its whole band is defensive); OPPORTUNITY deliberately carries none.
# The value is a policy constant (W1): an adaptive derived weight (W2, solved
# from a target equity quota) is a documented upgrade path, not implemented.
#
# BALANCED = 35 % per the 2026-09-14 corridor sweep (12-config BALANCED grid;
# equity quota incl. breakdown data + documented mixed-fund heuristic):
#   0 % → avg 86.9 % equity (80.9–90.7 %) — the pre-v4.1 problem
#   25 % → avg 65.8 %, 10/12 configs above the 65 % ceiling  → rejected
#   30 % → avg 61.3 %, max 63.7 % — passes, only 1.3 pp margin → runner-up
#   35 % → avg 57.3 % (52.3–59.7 %) — mid-corridor, robust margin → DEFAULT
ANCHOR_BUDGETS: Dict[str, float] = {
    "DEFENSIVE": 0.0,
    "BALANCED": 35.0,
    "OPPORTUNITY": 0.0,
}

PROFILES: tuple = ("DEFENSIVE", "BALANCED", "OPPORTUNITY")


def risk_band_for_profile(risk_profile: str) -> Dict[str, Any]:
    """Return the band parameters for a profile (unknown → BALANCED)."""
    return RISK_BANDS.get(risk_profile, RISK_BANDS["BALANCED"])


def satellite_total_cap_for_profile(risk_profile: str) -> float:
    """Return the satellite band cap (in %) for a profile (unknown → BALANCED)."""
    return SATELLITE_TOTAL_CAPS.get(
        risk_profile, SATELLITE_TOTAL_CAPS["BALANCED"]
    )


def anchor_budget_for_profile(risk_profile: str) -> float:
    """Return the defensive-anchor budget (in %) for a profile (unknown → BALANCED)."""
    return ANCHOR_BUDGETS.get(risk_profile, ANCHOR_BUDGETS["BALANCED"])


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fund_in_risk_band(fund: Dict[str, Any], band: Dict[str, Any]) -> bool:
    """Return True if fund satisfies SRRI, and (when present) volatility and MDD checks.

    Mirrors the engine's eligibility semantics exactly: ``srri`` falls back to
    ``risk_level`` when absent; ``volatility``/``max_drawdown`` are optional —
    a fund without the field is not excluded by it (same leniency the engine
    applies, so advisor and backstop never disagree about membership).
    """
    srri = fund.get("srri") if fund.get("srri") is not None else fund.get("risk_level")
    if srri is None:
        return False
    srri_val = float(srri)
    if not (band["srri_min"] <= srri_val <= band["srri_max"]):
        return False

    vol = fund.get("volatility")
    if vol is not None:
        vol_f = _as_float(vol)
        vol_max = band.get("vol_max")
        vol_min = band.get("vol_min")
        if vol_max is not None and vol_f > vol_max:
            return False
        if vol_min is not None and vol_f < vol_min:
            return False

    mdd = fund.get("max_drawdown")
    if mdd is not None:
        if _as_float(mdd) > band["mdd_max"]:
            return False

    return True


def funds_in_band(
    funds: List[Dict[str, Any]], risk_profile: str
) -> List[Dict[str, Any]]:
    """All funds that satisfy the band for ``risk_profile`` (engine-equivalent)."""
    band = risk_band_for_profile(risk_profile)
    return [f for f in funds if fund_in_risk_band(f, band)]
