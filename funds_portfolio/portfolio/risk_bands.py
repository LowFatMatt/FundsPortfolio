"""Shared risk-band definitions — the single source of truth.

The bands were extracted from ``decision_engine.py`` so the dialog layer
(feasibility advisor, questionnaire loader) can evaluate "would this fund be
selectable for this risk profile?" without importing the whole engine or —
worse — re-declaring the band values. The engine delegates to this module;
Slide 8 of the Provinzial spec remains the ultimate authority for the values.

Used by:
  * ``DecisionEngine._risk_band_for_profile`` / ``_fund_in_risk_band`` (hard
    filter — the compliance backstop),
  * ``funds_portfolio/dialog/feasibility.py`` (dialog answer-space shaping).
"""

from __future__ import annotations

from typing import Any, Dict, List

# NOTE: Slide 8 is the ultimate truth specifying the risk bands.
# The document contains other values in further slides which
# do not reflect the final specification.
RISK_BANDS: Dict[str, Dict[str, Any]] = {
    "DEFENSIVE": {
        "srri_min": 1,
        "srri_max": 3,
        "vol_max": 8.0,
        "vol_min": None,
        "mdd_max": 15.0,
    },
    "BALANCED": {
        "srri_min": 2,
        "srri_max": 5,
        "vol_max": 15.0,
        "vol_min": 5.0,  # reviewed 2: vol_min corrected to be 5.0 (see Spec. Pg./Sld. 8)
        "mdd_max": 30.0,
    },
    "OPPORTUNITY": {
        "srri_min": 4,
        "srri_max": 7,
        "vol_max": None,
        "vol_min": 10.0,
        "mdd_max": 50.0,
    },
}

PROFILES: tuple = ("DEFENSIVE", "BALANCED", "OPPORTUNITY")


def risk_band_for_profile(risk_profile: str) -> Dict[str, Any]:
    """Return the band parameters for a profile (unknown → BALANCED)."""
    return RISK_BANDS.get(risk_profile, RISK_BANDS["BALANCED"])


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
