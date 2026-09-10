"""Feasibility advisor v2 — pure answer-space shaping functions.

Answers the question the dialog must ask before offering a choice:

    "Given the answers so far, can the selection engine still honor
     this option?" — where "answers so far" spans the risk approach AND
     the hard ESG / ETF preference filters.

Scope (v2):

* Both dimensions: preferred themes (upper-case values) and preferred
  regions (lower-case values), mirroring the engine's matching rules.
* L2 — option availability: every served option carries precomputed fund
  counts for each (risk profile × esg8_9 × etf_only) filter combination —
  12 integers per option under ``feasible``. The SPA resolves the live
  combination from the answers (risk/ESG/ETF questions precede
  regions/themes in schema order and in both flow variants) and disables
  chips whose count is zero. No dynamic endpoint needed; the loader
  recomputes on funds-DB refresh.
* L0 — option exclusions: whole answer options can be removed from the
  answer space per risk profile (``option_exclusions_by_profile``).
  Currently ``etf_only`` is excluded for DEFENSIVE and BALANCED: the
  ETF-only universe inside those bands is too small for diversified
  selection (data check 2026-09-10: DEFENSIVE etf_only leaves 1 of 4
  in-band funds, BALANCED 13 of 32 with collapsed theme breadth) and
  ``esg8_9+etf`` is empty for DEFENSIVE — a choice the engine could not
  honor (resolves user-journey decision D-19).
* L1 — combined cardinality: ONE budget across themes + regions,
  DEFENSIVE 1 / BALANCED 2 / OPPORTUNITY 3 (per-section ``max`` remains an
  additional cap), plus an optional per-field cap vector
  (``per_field_max_by_profile``): BALANCED additionally caps regions and
  themes at 1 each, so the only 2-selection composition is 1 region +
  1 theme — matching user expectations (2026-09 UX tests, resolves
  user-journey decision D-03). Declared in the schema's questionnaire-level
  ``preference_gating`` block; this module provides fallback defaults.

Design constraints:
  * Pure functions only (no I/O) — the loader/app pass the funds list in.
  * Band and ESG/ETF semantics are imported from ``portfolio.risk_bands``
    and ``portfolio.eligibility`` (the modules the engine delegates to),
    so advisor and backstop can never disagree.
  * Tolerant of unknown/legacy answers: unknown risk answer → no gating;
    unknown value → no pruning; "none" → never gated; PREFER_ESG and
    prefer_etf never gate (they boost, never exclude — engine semantics).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..portfolio.eligibility import (
    ESG_ONLY_VALUE,
    ETF_ONLY_VALUE,
    is_esg_fund,
    normalise_esg_preference,
)
from ..portfolio.risk_bands import PROFILES, RISK_BANDS, fund_in_risk_band

# Answer fields the gating depends on.
RISK_FIELD = "risk_approach"
ESG_FIELD = "esg_preference"
ETF_FIELD = "etf_preference"

# risk_approach answer value → optimizer risk profile. Mirrors the
# ``optimizer_profile`` attributes on the schema's risk_approach options.
ANSWER_TO_PROFILE: Dict[str, str] = {
    "conservative": "DEFENSIVE",
    "moderate": "BALANCED",
    "aggressive": "OPPORTUNITY",
}

# Dimension registry: answer field, value normalisation (mirrors the
# engine's `_fund_theme` upper / `_fund_region` lower matching), and the
# no-preference placeholder set that is never gated.
DIMENSIONS: Dict[str, Dict[str, Any]] = {
    "theme": {
        "field": "preferred_themes",
        "normalise": str.upper,
        "skip": {"NONE"},
    },
    "region": {
        "field": "preferred_regions",
        "normalise": str.lower,
        "skip": set(),
    },
}

# Answer fields sharing one selection budget.
BUDGET_FIELDS = ("preferred_regions", "preferred_themes")

# Filter-combination keys for the precomputed per-option counts.
# "esg8_9" = ART_8_9_ONLY active, "etf" = etf_only active, "+" = both.
COMBO_KEYS = ("any", "esg8_9", "etf", "esg8_9+etf")

# Fallback combined budget (L1) per profile when the schema's
# preference_gating block is absent.
DEFAULT_MAX_BY_PROFILE: Dict[str, int] = {
    "DEFENSIVE": 1,
    "BALANCED": 2,
    "OPPORTUNITY": 3,
}

# Fallback per-field caps (L1 composition) when the schema's
# preference_gating block is absent: BALANCED must not spend its budget of 2
# on a single dimension (2 regions or 2 themes) — 1 region + 1 theme is the
# composition users expect. Profiles without an entry have no per-field cap
# (pure shared budget, DEF/OPP behaviour unchanged).
DEFAULT_PER_FIELD_MAX_BY_PROFILE: Dict[str, Dict[str, int]] = {
    "BALANCED": {"preferred_regions": 1, "preferred_themes": 1},
}

# Fallback option exclusions (L0) when the schema's preference_gating block
# is absent: ``etf_only`` is not offered under DEFENSIVE/BALANCED — see the
# module docstring for the data rationale. Profiles without an entry keep
# every option. Mirrored in the schema's
# ``preference_gating.option_exclusions_by_profile``.
DEFAULT_EXCLUDED_OPTIONS_BY_PROFILE: Dict[str, Dict[str, List[str]]] = {
    "DEFENSIVE": {"etf_preference": ["etf_only"]},
    "BALANCED": {"etf_preference": ["etf_only"]},
}

# Fallback downgrade map for defensive trims: when a stored/prefilled answer
# carries an excluded value (legacy portfolio, deep-link, back-navigation),
# it is replaced by this fallback before submission. Mirrored in the
# schema's ``preference_gating.option_fallbacks``.
DEFAULT_OPTION_FALLBACKS: Dict[str, str] = {"etf_only": "prefer_etf"}

# The no-preference placeholder — valid answer, never gated, never counted.
THEME_NONE = "none"


def _empty_counts() -> Dict[str, Dict[str, int]]:
    return {p: {k: 0 for k in COMBO_KEYS} for p in PROFILES}


def risk_profile_for_answer(risk_answer: Any) -> Optional[str]:
    """Map a ``risk_approach`` answer to its risk profile (None if unknown)."""
    if not isinstance(risk_answer, str):
        return None
    return ANSWER_TO_PROFILE.get(risk_answer.strip().lower())


def combo_key(esg_answer: Any, etf_answer: Any) -> str:
    """Live filter combination for the ESG/ETF answers.

    Mirrors the engine exactly: only ART_8_9_ONLY and etf_only hard-filter
    (legacy ESG answers are normalised first); PREFER_ESG / prefer_etf map
    to "any".
    """
    esg_on = normalise_esg_preference(esg_answer) == ESG_ONLY_VALUE
    etf_on = str(etf_answer or "").strip() == ETF_ONLY_VALUE
    if esg_on and etf_on:
        return "esg8_9+etf"
    if esg_on:
        return "esg8_9"
    if etf_on:
        return "etf"
    return "any"


def value_feasible_counts(
    funds: List[Dict[str, Any]], dimension: str
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Per option value: in-band fund counts for every filter combination.

    Returns ``{VALUE: {PROFILE: {combo: count}}}`` where a fund counts
    toward combo X iff it is in-band for the profile AND would survive
    filter combination X (a non-ESG fund still counts under "etf", etc.).
    Funds without the dimension value back no option and are skipped.
    """
    cfg = DIMENSIONS[dimension]
    normalise = cfg["normalise"]
    counts: Dict[str, Dict[str, Dict[str, int]]] = {}
    for fund in funds:
        raw = str(fund.get(dimension) or "").strip()
        if not raw:
            continue
        value = normalise(raw)
        if value in cfg["skip"]:
            continue
        per_value = counts.setdefault(value, _empty_counts())
        esg_ok = is_esg_fund(fund)
        etf_ok = bool(fund.get("is_etf"))
        fund_combos = ["any"]
        if esg_ok:
            fund_combos.append("esg8_9")
        if etf_ok:
            fund_combos.append("etf")
        if esg_ok and etf_ok:
            fund_combos.append("esg8_9+etf")
        for profile in PROFILES:
            if fund_in_risk_band(fund, RISK_BANDS[profile]):
                for key in fund_combos:
                    per_value[profile][key] += 1
    return counts


def theme_counts(funds: List[Dict[str, Any]]):
    """Feasible-combination counts keyed by theme (upper-case)."""
    return value_feasible_counts(funds, "theme")


def region_counts(funds: List[Dict[str, Any]]):
    """Feasible-combination counts keyed by region (lower-case)."""
    return value_feasible_counts(funds, "region")


def decorate_options(
    options: List[Dict[str, Any]],
    counts: Dict[str, Dict[str, Dict[str, int]]],
    dimension: str,
) -> List[Dict[str, Any]]:
    """Attach a ``feasible`` combination-count table to each option (by value).

    The SPA combines these with the questionnaire-level ``preference_gating``
    block to disable chips per live answers. Options keep their identity —
    this only adds metadata.
    """
    cfg = DIMENSIONS[dimension]
    for opt in options:
        raw = str(opt.get("value") or "").strip()
        if not raw:
            continue
        value = cfg["normalise"](raw)
        if value in cfg["skip"]:
            continue
        opt["feasible"] = counts.get(value, _empty_counts())
    return options


def decorate_theme_options(options, counts):
    return decorate_options(options, counts, "theme")


def decorate_region_options(options, counts):
    return decorate_options(options, counts, "region")


def combined_budget(
    gating: Optional[Dict[str, Any]], risk_answer: Any
) -> Optional[int]:
    """Combined theme+region selection budget for the risk answer.

    ``gating`` is the questionnaire-level ``preference_gating`` block; when
    absent the module defaults (1/2/3) apply. None when the risk answer is
    unknown (no gating).
    """
    profile = risk_profile_for_answer(risk_answer)
    if profile is None:
        return None
    declared = (gating or {}).get("budget", {}).get("max_by_profile") or {}
    # Partial declarations fall back per-profile, so an override for one
    # profile never blanks the others.
    value = declared.get(profile, DEFAULT_MAX_BY_PROFILE.get(profile))
    return int(value) if isinstance(value, (int, float)) else None


def per_field_budget(
    gating: Optional[Dict[str, Any]], risk_answer: Any, field: str
) -> Optional[int]:
    """Per-field composition cap (L1) for the risk answer and budget field.

    ``gating`` is the questionnaire-level ``preference_gating`` block; the
    optional ``budget.per_field_max_by_profile`` maps profile → field → max.
    When the block or the profile entry is absent the module defaults apply
    (BALANCED: regions/themes ≤ 1 each; DEF/OPP: no per-field cap → None).
    None means "no per-field cap" — the shared combined budget still applies.
    """
    profile = risk_profile_for_answer(risk_answer)
    if profile is None:
        return None
    declared = (
        (gating or {}).get("budget", {}).get("per_field_max_by_profile") or {}
    )
    defaults = DEFAULT_PER_FIELD_MAX_BY_PROFILE.get(profile) or {}
    # Per-field fallback (mirrors combined_budget's per-profile fallback):
    # a declaration that overrides one field never blanks the others.
    per_profile = declared.get(profile)
    value = (
        per_profile.get(field)
        if isinstance(per_profile, dict)
        else None
    )
    if value is None:
        value = defaults.get(field)
    return int(value) if isinstance(value, (int, float)) else None


def excluded_options(
    gating: Optional[Dict[str, Any]], risk_answer: Any, field: str
) -> List[str]:
    """Option values excluded from the answer space (L0) for the risk answer.

    ``gating`` is the questionnaire-level ``preference_gating`` block; the
    optional ``option_exclusions_by_profile`` maps profile → field → list of
    excluded option values. When the block or the profile entry is absent
    the module defaults apply (DEF/BAL: ``etf_only`` excluded; OPP: none).
    """
    profile = risk_profile_for_answer(risk_answer)
    if profile is None:
        return []
    declared = (gating or {}).get("option_exclusions_by_profile") or {}
    defaults_map = DEFAULT_EXCLUDED_OPTIONS_BY_PROFILE.get(profile) or {}
    # Per-field fallback (mirrors per_field_budget): a declaration that
    # overrides one field never blanks the others.
    per_profile = declared.get(profile)
    values = per_profile.get(field) if isinstance(per_profile, dict) else None
    if values is None:
        values = defaults_map.get(field)
    if not isinstance(values, list):
        return []
    return [str(v) for v in values]


def option_fallback(gating: Optional[Dict[str, Any]], value: Any) -> str:
    """Downgrade target for an excluded option value (defensive trim).

    ``gating`` is the questionnaire-level ``preference_gating`` block; the
    optional ``option_fallbacks`` maps value → replacement. Values without a
    declared or default fallback are returned unchanged.
    """
    raw = str(value or "").strip()
    if not raw:
        return raw
    declared = (gating or {}).get("option_fallbacks") or {}
    return str(declared.get(raw) or DEFAULT_OPTION_FALLBACKS.get(raw) or raw)


def selected_values(answers: Dict[str, Any], field: str) -> List[str]:
    """Normalised selected values of a multi-select answer field."""
    raw = answers.get(field)
    if not isinstance(raw, list):
        return []
    return [str(v).strip() for v in raw if str(v or "").strip()]


def combined_selection_count(answers: Dict[str, Any]) -> int:
    """Number of real theme/region selections across the budget fields.

    No-preference placeholders ("none") never count.
    """
    total = 0
    for field in BUDGET_FIELDS:
        for value in selected_values(answers, field):
            if value.lower() != THEME_NONE:
                total += 1
    return total


def unavailable_values(
    answers: Dict[str, Any], funds: List[Dict[str, Any]], dimension: str
) -> List[str]:
    """Selected values of a dimension with zero funds under the live answers.

    Empty when the risk answer is unknown — without a profile there is no
    band to check against. ESG/ETF answers resolve via ``combo_key``.
    """
    profile = risk_profile_for_answer(answers.get(RISK_FIELD))
    if profile is None:
        return []
    key = combo_key(answers.get(ESG_FIELD), answers.get(ETF_FIELD))
    counts = value_feasible_counts(funds, dimension)
    cfg = DIMENSIONS[dimension]
    out: List[str] = []
    for value in selected_values(answers, cfg["field"]):
        norm = cfg["normalise"](value)
        if norm in cfg["skip"]:
            continue
        if counts.get(norm, _empty_counts())[profile].get(key, 0) == 0:
            out.append(norm)
    return out


def feasibility_warnings(
    answers: Dict[str, Any], funds: List[Dict[str, Any]]
) -> List[str]:
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
    key = combo_key(answers.get(ESG_FIELD), answers.get(ETF_FIELD))
    filter_desc = {
        "any": "",
        "esg8_9": " + ESG-only filter (SFDR Article 8/9)",
        "etf": " + ETF-only filter",
        "esg8_9+etf": " + ESG-only and ETF-only filters",
    }[key]

    for dimension in ("theme", "region"):
        field = DIMENSIONS[dimension]["field"]
        for value in unavailable_values(answers, funds, dimension):
            warnings.append(
                f'"{field}" includes "{value.lower()}" but the funds universe has '
                f"no matching fund inside the {profile} risk band "
                f"({band_desc}){filter_desc}; "
                "the selection engine cannot honor this preference"
            )

    # L0 exclusions: values the answer space never offered for this profile
    # (etf_only under DEFENSIVE/BALANCED) — legacy/prefilled answers only.
    etf_answer = str(answers.get(ETF_FIELD) or "").strip()
    if etf_answer and etf_answer in excluded_options(
        None, answers.get(RISK_FIELD), ETF_FIELD
    ):
        warnings.append(
            f'"etf_preference" = "{etf_answer}" is excluded for the {profile} '
            "risk approach (the ETF-only universe inside this risk band is too "
            "small for diversified selection); such answers are downgraded to "
            f'"{option_fallback(None, etf_answer)}"'
        )

    budget = combined_budget(None, answers.get(RISK_FIELD))
    total = combined_selection_count(answers)
    if budget is not None and total > budget:
        warnings.append(
            f"combined theme/region selections ({total}) exceed the {profile} "
            f"budget of {budget}; expect reduced coverage or "
            "diversified-away preferences"
        )

    # L1 composition: per-field caps (BALANCED: regions/themes ≤ 1 each).
    for field in BUDGET_FIELDS:
        field_budget = per_field_budget(None, answers.get(RISK_FIELD), field)
        if field_budget is None:
            continue
        field_count = sum(
            1
            for value in selected_values(answers, field)
            if value.lower() != THEME_NONE
        )
        if field_count > field_budget:
            warnings.append(
                f'"{field}" has {field_count} selections but the {profile} '
                f"composition allows at most {field_budget} per dimension "
                "(e.g. BALANCED expects 1 region + 1 theme, not 2 of one kind)"
            )

    return warnings
