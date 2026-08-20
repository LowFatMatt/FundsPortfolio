"""Feasibility advisor — pure answer-space shaping functions.

Answers the question the dialog must ask before offering a choice:

    "Given the answers so far, can the selection engine still honor
     this option within the user's risk band?"

Pilot scope (themes × risk):

* L2 — option availability: a theme option is only selectable when the
  funds universe contains at least one in-band fund for the risk profile
  implied by ``risk_approach``. The QuestionnaireLoader attaches the
  per-profile in-band counts to every served theme option; the SPA uses
  them to render infeasible chips as disabled-with-reason.
* L1 — cardinality: the effective ``max`` number of theme selections is
  profile-dependent (conservative → 1). Declared in the schema's
  ``gating`` block; this module provides the fallback defaults.

Design constraints:
  * Pure functions only (no I/O) — the loader/app pass the funds list in.
  * Band definitions are imported from ``portfolio.risk_bands`` (the same
    module the engine delegates to), so advisor and backstop can never
    disagree about which fund is in-band.
  * Tolerant of unknown/legacy answers: unknown risk answer → no gating,
    unknown theme → no pruning, "none" → never gated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..portfolio.risk_bands import PROFILES, RISK_BANDS, fund_in_risk_band

# The questionnaire field whose answer drives the gating.
RISK_FIELD = "risk_approach"

# risk_approach answer value → optimizer risk profile. Mirrors the
# ``optimizer_profile`` attributes on the schema's risk_approach options.
ANSWER_TO_PROFILE: Dict[str, str] = {
    "conservative": "DEFENSIVE",
    "moderate": "BALANCED",
    "aggressive": "OPPORTUNITY",
}

# Fallback cardinality (L1) per profile when the schema's gating block is
# absent. Conservative users get one theme: thematic funds skew volatile,
# so a conservative band can host at most a small satellite position.
DEFAULT_MAX_BY_PROFILE: Dict[str, int] = {
    "DEFENSIVE": 1,
    "BALANCED": 2,
    "OPPORTUNITY": 2,
}

# The no-preference placeholder — valid answer, never gated.
THEME_NONE = "none"


def risk_profile_for_answer(risk_answer: Any) -> Optional[str]:
    """Map a ``risk_approach`` answer to its risk profile (None if unknown)."""
    if not isinstance(risk_answer, str):
        return None
    return ANSWER_TO_PROFILE.get(risk_answer.strip().lower())


def theme_band_counts(funds: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Per theme: how many funds are in-band for each risk profile.

    Returns ``{THEME_UPPER: {"DEFENSIVE": n, "BALANCED": n, "OPPORTUNITY": n}}``.
    Funds without a theme (or theme ``NONE``) back no option and are skipped.
    """
    counts: Dict[str, Dict[str, int]] = {}
    for fund in funds:
        raw = str(fund.get("theme") or "").strip().upper()
        if not raw or raw == "NONE":
            continue
        per_theme = counts.setdefault(raw, {p: 0 for p in PROFILES})
        for profile in PROFILES:
            if fund_in_risk_band(fund, RISK_BANDS[profile]):
                per_theme[profile] += 1
    return counts


def decorate_theme_options(
    options: List[Dict[str, Any]], counts: Dict[str, Dict[str, int]]
) -> List[Dict[str, Any]]:
    """Attach an ``in_band`` per-profile count to each theme option (by value).

    The decorated options are what the loader serves; the SPA combines them
    with the section's ``gating`` block to disable chips per risk answer.
    Options keep their identity — this only adds metadata.
    """
    for opt in options:
        value = str(opt.get("value") or "").strip().upper()
        if value and value != "NONE":
            opt["in_band"] = dict(counts.get(value, {p: 0 for p in PROFILES}))
    return options


def effective_theme_max(
    gating: Optional[Dict[str, Any]], risk_answer: Any
) -> Optional[int]:
    """Effective number of selectable themes for the current risk answer.

    ``gating`` is the section's declaration from the schema
    (``{"field": ..., "max_by_profile": {...}}``); when absent the module
    defaults apply. Returns None when the risk answer is unknown (no gating).
    """
    profile = risk_profile_for_answer(risk_answer)
    if profile is None:
        return None
    max_by_profile = (gating or {}).get("max_by_profile") or DEFAULT_MAX_BY_PROFILE
    value = max_by_profile.get(profile)
    return int(value) if isinstance(value, (int, float)) else None


def selected_themes(answers: Dict[str, Any]) -> List[str]:
    """Normalised (upper-case) selected theme values from the answers."""
    raw = answers.get("preferred_themes")
    if not isinstance(raw, list):
        return []
    return [str(t).strip().upper() for t in raw if str(t or "").strip()]


def unavailable_themes(
    answers: Dict[str, Any], funds: List[Dict[str, Any]]
) -> List[str]:
    """Selected themes with zero in-band funds for the answered risk profile.

    Empty when the risk answer is unknown — without a profile there is no
    band to check against (mirrors the engine's fallback-to-BALANCED only
    at selection time, not at dialog time).
    """
    profile = risk_profile_for_answer(answers.get(RISK_FIELD))
    if profile is None:
        return []
    counts = theme_band_counts(funds)
    return [
        t
        for t in selected_themes(answers)
        if t != "NONE" and counts.get(t, {p: 0 for p in PROFILES}).get(profile, 0) == 0
    ]


def feasibility_warnings(answers: Dict[str, Any], funds: List[Dict[str, Any]]) -> List[str]:
    """Soft-validation warnings for answer combinations the engine cannot honor.

    Never rejects: the caller logs these (portfolio logs / decision trace
    context). Legacy portfolios and the eval answer grid stay valid.
    """
    warnings: List[str] = []
    profile = risk_profile_for_answer(answers.get(RISK_FIELD))
    if profile is None:
        return warnings

    band = RISK_BANDS[profile]
    band_desc = (
        f"SRRI {band['srri_min']}-{band['srri_max']}"
        f", vol<={band['vol_max'] if band['vol_max'] is not None else '∞'}"
        f", MDD<={band['mdd_max']}"
    )

    for theme in unavailable_themes(answers, funds):
        warnings.append(
            f'preferred_themes includes "{theme.lower()}" but the funds universe has '
            f"no matching fund inside the {profile} risk band ({band_desc}); "
            "the selection engine cannot honor this preference"
        )

    max_sel = effective_theme_max(None, answers.get(RISK_FIELD))
    themes = [t for t in selected_themes(answers) if t != "NONE"]
    if max_sel is not None and len(themes) > max_sel:
        warnings.append(
            f"preferred_themes has {len(themes)} selections but the {profile} "
            f"risk approach supports at most {max_sel} thematic satellite "
            "position(s); expect reduced coverage or diversified-away preferences"
        )

    return warnings
