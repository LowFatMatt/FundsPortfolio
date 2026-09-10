"""Tests for the dialog feasibility advisor v2 (answer-space shaping).

Covers:
  * pure advisor functions (mapping, filter combinations, per-dimension
    feasible counts, combined budget, cross-filter warnings),
  * the exact scenario from portfolios/port_20260831_38d855c6.json
    (aggressive + ART_8_9_ONLY + etf_only + technology → unfulfillable),
  * loader integration (both region and theme options decorated),
  * engine regression (shared eligibility/band modules keep the backstop
    identical).
"""

import json

import pytest

from funds_portfolio.dialog import feasibility as feas
from funds_portfolio.portfolio import risk_bands
from funds_portfolio.portfolio.decision_engine import DecisionEngine
from funds_portfolio.questionnaire.loader import QuestionnaireLoader


# --- fixtures ---------------------------------------------------------------


def make_fund(**overrides):
    fund = {
        "isin": "XX",
        "srri": 4,
        "volatility": 10.0,
        "max_drawdown": 20.0,
        "esg_label": "LOW",
        "is_etf": False,
    }
    fund.update(overrides)
    return fund


@pytest.fixture
def funds():
    """Synthetic universe reproducing the port_20260831_38d855c6 trap.

    * TECHNOLOGY has two OPPORTUNITY funds — one active Article 8 (survives
      ESG-only), one non-ESG ETF (survives ETF-only) — but NOTHING survives
      both: under "esg8_9+etf" the theme is unfulfillable.
    * SUSTAINABILITY has one defensive-capable Article 9 ETF.
    * Region "Europe" is backed by one active non-ESG fund (OPPORTUNITY only).
    """
    return [
        make_fund(
            isin="T1",
            theme="TECHNOLOGY",
            srri=6,
            volatility=20.0,
            max_drawdown=40.0,
            esg_label="SFDR_ARTICLE_8",
            is_etf=False,
        ),
        make_fund(
            isin="T2",
            theme="TECHNOLOGY",
            srri=6,
            volatility=18.0,
            max_drawdown=35.0,
            esg_label="LOW",
            is_etf=True,
        ),
        make_fund(
            isin="S1",
            theme="SUSTAINABILITY",
            srri=3,
            volatility=5.0,
            max_drawdown=10.0,
            esg_label="SFDR_ARTICLE_9",
            is_etf=True,
        ),
        make_fund(
            isin="R1",
            region="Europe",
            srri=5,
            volatility=12.0,
            max_drawdown=25.0,
            esg_label="LOW",
            is_etf=False,
        ),
    ]


# --- mapping + filter combinations ------------------------------------------


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("conservative", "DEFENSIVE"),
        ("moderate", "BALANCED"),
        ("aggressive", "OPPORTUNITY"),
        ("Conservative", "DEFENSIVE"),
        ("", None),
        ("unknown", None),
        (None, None),
        (123, None),
    ],
)
def test_risk_profile_for_answer(answer, expected):
    assert feas.risk_profile_for_answer(answer) == expected


@pytest.mark.parametrize(
    "esg,etf,expected",
    [
        ("NONE", "no_preference", "any"),
        ("PREFER_ESG", "prefer_etf", "any"),  # soft prefs never gate
        ("ART_8_9_ONLY", "no_preference", "esg8_9"),
        ("NONE", "etf_only", "etf"),
        ("ART_8_9_ONLY", "etf_only", "esg8_9+etf"),
        ("esg_enhanced", None, "esg8_9"),  # legacy answer
        (None, None, "any"),
    ],
)
def test_combo_key(esg, etf, expected):
    assert feas.combo_key(esg, etf) == expected


# --- per-dimension feasible counts -------------------------------------------


def test_theme_counts_cross_filter_combinations(funds):
    counts = feas.theme_counts(funds)

    tech = counts["TECHNOLOGY"]["OPPORTUNITY"]
    assert tech["any"] == 2
    assert tech["esg8_9"] == 1  # the active Article 8 fund
    assert tech["etf"] == 1  # the non-ESG ETF
    assert tech["esg8_9+etf"] == 0  # ← the port_20260831_38d855c6 trap

    susi = counts["SUSTAINABILITY"]["DEFENSIVE"]
    assert susi == {"any": 1, "esg8_9": 1, "etf": 1, "esg8_9+etf": 1}


def test_region_counts_normalisation(funds):
    counts = feas.region_counts(funds)
    assert counts["europe"]["OPPORTUNITY"]["any"] == 1  # "Europe" → europe
    assert counts["europe"]["OPPORTUNITY"]["esg8_9"] == 0
    assert "germany" not in counts


def test_unthemed_funds_back_no_option(funds):
    counts = feas.theme_counts(funds)
    assert "NONE" not in counts


def test_decorate_options_both_dimensions(funds):
    theme_opts = [
        {"id": "theme_technology", "value": "technology"},
        {"id": "theme_none", "value": "none"},
    ]
    feas.decorate_theme_options(theme_opts, feas.theme_counts(funds))
    assert theme_opts[0]["feasible"]["OPPORTUNITY"]["esg8_9+etf"] == 0
    assert "feasible" not in theme_opts[1]  # "none" never decorated

    region_opts = [
        {"id": "region_europe", "value": "europe"},
        {"id": "region_north_america", "value": "north_america"},
    ]
    feas.decorate_region_options(region_opts, feas.region_counts(funds))
    assert region_opts[0]["feasible"]["OPPORTUNITY"]["any"] == 1
    # Unbacked canonical regions surface as all-zero tables, not gaps.
    assert all(n == 0 for n in region_opts[1]["feasible"]["OPPORTUNITY"].values())


# --- combined budget (L1) -----------------------------------------------------


def test_combined_budget_defaults():
    assert feas.combined_budget(None, "conservative") == 1
    assert feas.combined_budget(None, "moderate") == 2
    assert feas.combined_budget(None, "aggressive") == 3
    assert feas.combined_budget(None, "unknown-answer") is None


def test_combined_budget_respects_gating_block():
    gating = {"budget": {"max_by_profile": {"DEFENSIVE": 2}}}
    assert feas.combined_budget(gating, "conservative") == 2
    assert feas.combined_budget(gating, "moderate") == 2  # module default


def test_combined_selection_count_ignores_placeholders():
    answers = {
        "preferred_regions": ["europe", "asia"],
        "preferred_themes": ["technology", "none"],
    }
    assert feas.combined_selection_count(answers) == 3


# --- per-field composition cap (L1, D-03) -------------------------------------


def test_per_field_budget_defaults():
    # BALANCED: regions/themes ≤ 1 each (the only 2-selection composition is
    # 1 region + 1 theme). DEF/OPP and unknown answers have no per-field cap.
    assert feas.per_field_budget(None, "moderate", "preferred_regions") == 1
    assert feas.per_field_budget(None, "moderate", "preferred_themes") == 1
    assert feas.per_field_budget(None, "conservative", "preferred_regions") is None
    assert feas.per_field_budget(None, "conservative", "preferred_themes") is None
    assert feas.per_field_budget(None, "aggressive", "preferred_regions") is None
    assert feas.per_field_budget(None, "aggressive", "preferred_themes") is None
    assert feas.per_field_budget(None, "unknown-answer", "preferred_regions") is None


def test_per_field_budget_respects_gating_block():
    gating = {
        "budget": {
            "per_field_max_by_profile": {
                "BALANCED": {"preferred_regions": 2},
            }
        }
    }
    assert feas.per_field_budget(gating, "moderate", "preferred_regions") == 2
    # Partial declaration: other fields fall back per-field.
    assert feas.per_field_budget(gating, "moderate", "preferred_themes") == 1
    # Other profiles are unaffected by the BALANCED override.
    assert feas.per_field_budget(gating, "conservative", "preferred_regions") is None
    assert feas.per_field_budget(gating, "aggressive", "preferred_themes") is None


def test_warnings_balanced_two_regions_composition(funds):
    """2 regions + 0 themes: within the combined budget of 2 but violates
    the per-field composition cap — the UX-test finding (D-03)."""
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_themes": [],
        "preferred_regions": ["europe", "asia"],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert any(
        '"preferred_regions"' in w and "at most 1" in w and "BALANCED" in w
        for w in warnings
    )


def test_warnings_balanced_two_themes_composition(funds):
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_themes": ["sustainability", "technology"],
        "preferred_regions": [],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert any('"preferred_themes"' in w and "at most 1" in w for w in warnings)


def test_warnings_balanced_one_region_one_theme_is_silent(funds):
    """The expected BALANCED composition: 1 region + 1 theme, no warnings
    (values backed by BALANCED-band funds)."""
    balanced_backed = funds + [
        make_fund(
            isin="R2",
            region="Europe",
            srri=3,
            volatility=8.0,
            max_drawdown=12.0,
            esg_label="LOW",
            is_etf=False,
        )
    ]
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_themes": ["sustainability"],
        "preferred_regions": ["europe"],
    }
    assert feas.feasibility_warnings(answers, balanced_backed) == []


def test_warnings_opportunity_two_regions_stay_silent(funds):
    """OPPORTUNITY has no per-field cap: 2 regions + 1 theme is valid."""
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_themes": ["technology"],
        "preferred_regions": ["europe", "asia"],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert not any("composition" in w for w in warnings)


# --- option exclusions (L0, D-19: etf_only under DEFENSIVE/BALANCED) ------------


def test_excluded_options_defaults():
    """etf_only is never offered under DEFENSIVE/BALANCED; OPP keeps every
    option; unknown answers and other fields are unaffected."""
    assert feas.excluded_options(None, "conservative", "etf_preference") == ["etf_only"]
    assert feas.excluded_options(None, "moderate", "etf_preference") == ["etf_only"]
    assert feas.excluded_options(None, "aggressive", "etf_preference") == []
    assert feas.excluded_options(None, "unknown-answer", "etf_preference") == []
    assert feas.excluded_options(None, "conservative", "esg_preference") == []


def test_excluded_options_respects_gating_block():
    gating = {
        "option_exclusions_by_profile": {
            # Declared empty list overrides the default for BALANCED.
            "BALANCED": {"etf_preference": []},
        }
    }
    assert feas.excluded_options(gating, "moderate", "etf_preference") == []
    # DEFENSIVE keeps its default via per-field fallback.
    assert feas.excluded_options(gating, "conservative", "etf_preference") == ["etf_only"]
    # OPPORTUNITY is unaffected either way.
    assert feas.excluded_options(gating, "aggressive", "etf_preference") == []


def test_option_fallback_defaults_and_override():
    assert feas.option_fallback(None, "etf_only") == "prefer_etf"
    assert feas.option_fallback(None, "no_preference") == "no_preference"
    assert feas.option_fallback(None, None) == ""
    assert (
        feas.option_fallback(
            {"option_fallbacks": {"etf_only": "no_preference"}}, "etf_only"
        )
        == "no_preference"
    )


def test_warnings_defensive_etf_only_excluded(funds):
    """Legacy/prefilled etf_only under DEFENSIVE: soft warning with the
    downgrade target (the SPA downgrades before submission)."""
    answers = {
        "risk_approach": "conservative",
        "esg_preference": "NONE",
        "etf_preference": "etf_only",
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert any(
        '"etf_preference"' in w
        and "etf_only" in w
        and "DEFENSIVE" in w
        and "prefer_etf" in w
        for w in warnings
    )


def test_warnings_balanced_etf_only_excluded(funds):
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "etf_only",
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert any("etf_only" in w and "BALANCED" in w for w in warnings)


def test_warnings_opportunity_etf_only_allowed(funds):
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "etf_only",
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert not any("excluded" in w for w in warnings)


# --- availability checks (L2) --------------------------------------------------


def test_portfolio_20260831_case_technology_unfulfillable(funds):
    """Exact reproduction of portfolios/port_20260831_38d855c6.json."""
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "ART_8_9_ONLY",
        "etf_preference": "etf_only",
        "preferred_themes": ["technology"],
        "preferred_regions": [],
    }
    assert feas.unavailable_values(answers, funds, "theme") == ["TECHNOLOGY"]


def test_feasible_without_filters(funds):
    answers = {"risk_approach": "aggressive", "preferred_themes": ["technology"]}
    assert feas.unavailable_values(answers, funds, "theme") == []


def test_region_unavailable_under_esg_filter(funds):
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "ART_8_9_ONLY",
        "preferred_regions": ["europe"],
    }
    assert feas.unavailable_values(answers, funds, "region") == ["europe"]


def test_unknown_risk_answer_disables_gating(funds):
    answers = {
        "risk_approach": "",
        "esg_preference": "ART_8_9_ONLY",
        "etf_preference": "etf_only",
        "preferred_themes": ["technology"],
    }
    assert feas.unavailable_values(answers, funds, "theme") == []


# --- soft warnings --------------------------------------------------------------


def test_feasibility_warnings_portfolio_case(funds):
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "ART_8_9_ONLY",
        "etf_preference": "etf_only",
        "preferred_themes": ["technology"],
        "preferred_regions": [],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert len(warnings) == 1
    assert "ESG-only and ETF-only filters" in warnings[0]
    assert '"technology"' in warnings[0]


def test_feasibility_warnings_budget_violation(funds):
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_themes": ["technology", "none"],
        "preferred_regions": ["europe", "asia", "germany"],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    # 1 theme + 3 regions = 4 selections > OPPORTUNITY budget of 3.
    assert any("budget of 3" in w for w in warnings)


def test_feasibility_warnings_feasible_answers_are_silent(funds):
    # D-19: etf_only is no longer silent under DEFENSIVE — the feasible
    # variant of the same ESG-strict combination uses prefer_etf instead.
    answers = {
        "risk_approach": "conservative",
        "esg_preference": "ART_8_9_ONLY",
        "etf_preference": "prefer_etf",
        "preferred_themes": ["sustainability"],
        "preferred_regions": [],
    }
    assert feas.feasibility_warnings(answers, funds) == []


# --- loader integration ----------------------------------------------------------

MINIMAL_SCHEMA = {
    "questionnaire": {
        "version": "2.1-test",
        "preference_gating": {
            "budget": {
                "fields": ["preferred_regions", "preferred_themes"],
                "max_by_profile": {"DEFENSIVE": 1, "BALANCED": 2, "OPPORTUNITY": 3},
            },
            "option_exclusions_by_profile": {
                "DEFENSIVE": {"etf_preference": ["etf_only"]},
                "BALANCED": {"etf_preference": ["etf_only"]},
            },
            "option_fallbacks": {"etf_only": "prefer_etf"},
        },
        "sections": [
            {
                "id": "preferred_regions",
                "name": "Regions",
                "type": "multi_select",
                "max": 2,
                "options": [],
            },
            {
                "id": "preferred_themes",
                "name": "Themes",
                "type": "multi_select",
                "max": 2,
                "options": [],
            },
        ],
    },
    "response_schema": {},
}


def _loader_with_db(tmp_path, funds_list):
    schema = tmp_path / "preferences_schema.json"
    schema.write_text(json.dumps(MINIMAL_SCHEMA), encoding="utf-8")
    funds_db = tmp_path / "funds_database.json"
    funds_db.write_text(json.dumps({"funds_database": funds_list}), encoding="utf-8")
    loader = QuestionnaireLoader(str(schema))
    # The loader resolves the funds DB from fixed container/cwd locations;
    # point it at the fixture explicitly (local runs have no root DB file).
    loader._funds_db_path = str(funds_db)
    assert loader._apply_dynamic_options()
    return loader


def test_loader_decorates_both_dimensions(tmp_path, funds):
    loader = _loader_with_db(tmp_path, funds)

    themes = {
        o["value"]: o for o in loader.get_section_by_id("preferred_themes")["options"]
    }
    regions = {
        o["value"]: o for o in loader.get_section_by_id("preferred_regions")["options"]
    }

    assert themes["technology"]["feasible"]["OPPORTUNITY"]["esg8_9+etf"] == 0
    assert regions["europe"]["feasible"]["OPPORTUNITY"]["any"] == 1
    # Unbacked canonical values surface as all-zero tables.
    assert all(n == 0 for n in themes["megatrends"]["feasible"]["OPPORTUNITY"].values())
    assert all(
        n == 0 for n in regions["north_america"]["feasible"]["BALANCED"].values()
    )


def test_loader_serves_preference_gating_block(tmp_path, funds):
    loader = _loader_with_db(tmp_path, funds)
    served = loader.get_questionnaire()
    assert served["preference_gating"]["budget"]["max_by_profile"] == {
        "DEFENSIVE": 1,
        "BALANCED": 2,
        "OPPORTUNITY": 3,
    }
    assert served["preference_gating"]["option_exclusions_by_profile"] == {
        "DEFENSIVE": {"etf_preference": ["etf_only"]},
        "BALANCED": {"etf_preference": ["etf_only"]},
    }
    assert served["preference_gating"]["option_fallbacks"] == {
        "etf_only": "prefer_etf",
    }
    translated = loader.get_questionnaire(language="de")
    assert translated["preference_gating"]["budget"]["fields"] == [
        "preferred_regions",
        "preferred_themes",
    ]
    assert translated["preference_gating"]["option_fallbacks"] == {
        "etf_only": "prefer_etf",
    }


# --- engine regression: shared modules keep the backstop identical ---------------


@pytest.mark.parametrize("profile", ["DEFENSIVE", "BALANCED", "OPPORTUNITY", "GARBAGE"])
def test_engine_band_delegation(profile):
    engine = DecisionEngine()
    assert engine._risk_band_for_profile(profile) == risk_bands.risk_band_for_profile(
        profile
    )


def test_engine_fund_in_risk_band_matches_shared_module(funds):
    engine = DecisionEngine()
    for profile in ("DEFENSIVE", "BALANCED", "OPPORTUNITY"):
        band = risk_bands.risk_band_for_profile(profile)
        for fund in funds:
            assert engine._fund_in_risk_band(
                fund, band
            ) == risk_bands.fund_in_risk_band(fund, band)


@pytest.mark.parametrize(
    "pref,expected",
    [
        ("ART_8_9_ONLY", "ART_8_9_ONLY"),
        ("esg_basic", "ART_8_9_ONLY"),  # legacy
        ("no_requirement", "NONE"),  # legacy
        ("PREFER_ESG", "PREFER_ESG"),
        ("garbage", "NONE"),
        (None, "NONE"),
    ],
)
def test_engine_esg_normaliser_delegation(pref, expected):
    assert DecisionEngine._normalise_esg_preference(pref) == expected


def test_engine_esg_fund_predicate_delegation(funds):
    engine = DecisionEngine()
    for fund in funds:
        assert engine._is_esg_fund(fund) == (
            fund["esg_label"].startswith("SFDR_ARTICLE")
        )


def test_band_values_unchanged():
    # Slide 8 values — frozen on purpose; a change here is a spec decision.
    # BALANCED is a documented deviation: post-v4 tightening, re-widened to
    # vol 15 % / MDD 25 % after real-universe testing (commit 2f66a73).
    assert risk_bands.RISK_BANDS["DEFENSIVE"] == {
        "srri_min": 1,
        "srri_max": 3,
        "vol_max": 8.0,
        "vol_min": None,
        "mdd_max": 15.0,
    }
    assert risk_bands.RISK_BANDS["BALANCED"] == {
        "srri_min": 2,
        "srri_max": 4,
        "vol_max": 15.0,
        "vol_min": 5.0,
        "mdd_max": 25.0,
    }
    assert risk_bands.RISK_BANDS["OPPORTUNITY"] == {
        "srri_min": 4,
        "srri_max": 7,
        "vol_max": None,
        "vol_min": 10.0,
        "mdd_max": 50.0,
    }


def test_satellite_total_caps_per_profile():
    # v4.1 allocation policy — frozen on purpose; a change here is a spec decision.
    assert risk_bands.SATELLITE_TOTAL_CAPS == {
        "DEFENSIVE": 30.0,
        "BALANCED": 30.0,
        "OPPORTUNITY": 40.0,
    }
    assert risk_bands.satellite_total_cap_for_profile("OPPORTUNITY") == 40.0
    assert risk_bands.satellite_total_cap_for_profile("BALANCED") == 30.0
    assert risk_bands.satellite_total_cap_for_profile("DEFENSIVE") == 30.0
    # Unknown profile falls back to BALANCED (mirrors risk_band_for_profile).
    assert risk_bands.satellite_total_cap_for_profile("NOPE") == 30.0
