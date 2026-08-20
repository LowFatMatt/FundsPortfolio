"""Tests for the dialog feasibility advisor (answer-space shaping pilot).

Covers:
  * pure advisor functions (mapping, counts, decoration, cardinality),
  * loader integration (served theme options carry per-profile in-band counts),
  * engine regression (shared risk bands keep the backstop identical).
"""

import json

import pytest

from funds_portfolio.dialog import feasibility as feas
from funds_portfolio.portfolio import risk_bands
from funds_portfolio.portfolio.decision_engine import DecisionEngine
from funds_portfolio.questionnaire.loader import QuestionnaireLoader


# --- fixtures ---------------------------------------------------------------

def make_fund(theme, srri, vol, mdd, isin="XX"):
    return {
        "isin": isin,
        "theme": theme,
        "srri": srri,
        "volatility": vol,
        "max_drawdown": mdd,
    }


@pytest.fixture
def funds():
    """Synthetic universe mirroring the shape of the general DB.

    * sustainability: one defensive-capable fund (SRRI 3, low vol/MDD),
                     one balanced-only fund (SRRI 4),
                     one aggressive-only fund (SRRI 6).
    * technology:     SRRI 6 only — never defensive-coverable.
    * commodities:    SRRI 6 with deep MDD — opportunity-only.
    """
    return [
        make_fund("SUSTAINABILITY", 3, 5.0, 10.0, "IE1"),
        make_fund("SUSTAINABILITY", 4, 10.0, 20.0, "IE2"),
        make_fund("SUSTAINABILITY", 6, 20.0, 40.0, "IE3"),
        make_fund("TECHNOLOGY", 6, 20.0, 40.0, "IE4"),
        make_fund("COMMODITIES", 6, 25.0, 45.0, "IE5"),
        make_fund("NONE", 2, 2.0, 5.0, "IE6"),  # unthemed funds back no option
        {"isin": "IE7", "theme": None, "srri": 2, "volatility": 2.0, "max_drawdown": 5.0},
    ]


# --- mapping ----------------------------------------------------------------

@pytest.mark.parametrize(
    "answer,expected",
    [
        ("conservative", "DEFENSIVE"),
        ("moderate", "BALANCED"),
        ("aggressive", "OPPORTUNITY"),
        ("Conservative", "DEFENSIVE"),  # tolerant normalisation
        ("", None),
        ("unknown", None),
        (None, None),
        (123, None),
    ],
)
def test_risk_profile_for_answer(answer, expected):
    assert feas.risk_profile_for_answer(answer) == expected


# --- per-theme in-band counts ----------------------------------------------

def test_theme_band_counts(funds):
    counts = feas.theme_band_counts(funds)
    assert counts["SUSTAINABILITY"] == {"DEFENSIVE": 1, "BALANCED": 2, "OPPORTUNITY": 2}
    assert counts["TECHNOLOGY"] == {"DEFENSIVE": 0, "BALANCED": 0, "OPPORTUNITY": 1}
    assert counts["COMMODITIES"] == {"DEFENSIVE": 0, "BALANCED": 0, "OPPORTUNITY": 1}
    # Unthemed / NONE funds back no option.
    assert "NONE" not in counts


def test_theme_band_counts_empty_universe():
    assert feas.theme_band_counts([]) == {}


def test_decorate_theme_options(funds):
    counts = feas.theme_band_counts(funds)
    options = [
        {"id": "theme_sustainability", "value": "sustainability", "label": "Sustainability"},
        {"id": "theme_technology", "value": "technology", "label": "Technology"},
        {"id": "theme_none", "value": "none", "label": "No specific theme"},
    ]
    decorated = feas.decorate_theme_options(options, counts)

    by_value = {o["value"]: o for o in decorated}
    assert by_value["sustainability"]["in_band"]["DEFENSIVE"] == 1
    assert by_value["technology"]["in_band"]["DEFENSIVE"] == 0
    # "none" is the no-preference placeholder — never decorated.
    assert "in_band" not in by_value["none"]


# --- cardinality (L1) --------------------------------------------------------

def test_effective_theme_max_defaults():
    assert feas.effective_theme_max(None, "conservative") == 1
    assert feas.effective_theme_max(None, "moderate") == 2
    assert feas.effective_theme_max(None, "aggressive") == 2
    assert feas.effective_theme_max(None, "unknown-answer") is None


def test_effective_theme_max_respects_gating_block():
    gating = {"max_by_profile": {"DEFENSIVE": 2, "BALANCED": 3, "OPPORTUNITY": 3}}
    assert feas.effective_theme_max(gating, "conservative") == 2
    assert feas.effective_theme_max(gating, "moderate") == 3


# --- availability checks (L2) ------------------------------------------------

def test_unavailable_themes_conservative(funds):
    answers = {
        "risk_approach": "conservative",
        "preferred_themes": ["sustainability", "technology"],
    }
    assert feas.unavailable_themes(answers, funds) == ["TECHNOLOGY"]


def test_unavailable_themes_balanced_commodities(funds):
    answers = {
        "risk_approach": "moderate",
        "preferred_themes": ["commodities", "sustainability"],
    }
    assert feas.unavailable_themes(answers, funds) == ["COMMODITIES"]


def test_unavailable_themes_none_placeholder_never_gated(funds):
    answers = {"risk_approach": "conservative", "preferred_themes": ["none"]}
    assert feas.unavailable_themes(answers, funds) == []


def test_unavailable_themes_unknown_risk_answer(funds):
    answers = {"risk_approach": "", "preferred_themes": ["technology"]}
    assert feas.unavailable_themes(answers, funds) == []


# --- soft warnings ------------------------------------------------------------

def test_feasibility_warnings_conservative(funds):
    answers = {
        "risk_approach": "conservative",
        "preferred_themes": ["sustainability", "technology"],
    }
    warnings = feas.feasibility_warnings(answers, funds)
    assert len(warnings) == 2
    assert any('"technology"' in w and "DEFENSIVE" in w for w in warnings)
    assert any("at most 1" in w for w in warnings)  # cardinality: 2 > 1


def test_feasibility_warnings_feasible_answers_are_silent(funds):
    answers = {
        "risk_approach": "aggressive",
        "preferred_themes": ["technology", "commodities"],
    }
    assert feas.feasibility_warnings(answers, funds) == []


def test_feasibility_warnings_unknown_risk_is_silent(funds):
    assert feas.feasibility_warnings({"preferred_themes": ["technology"]}, funds) == []


# --- loader integration --------------------------------------------------------

MINIMAL_SCHEMA = {
    "questionnaire": {
        "version": "2.0-test",
        "sections": [
            {
                "id": "preferred_themes",
                "name": "Themes",
                "type": "multi_select",
                "max": 2,
                "options": [],
            }
        ],
    },
    "response_schema": {},
}


def test_loader_decorates_theme_options(tmp_path):
    schema = tmp_path / "preferences_schema.json"
    schema.write_text(json.dumps(MINIMAL_SCHEMA), encoding="utf-8")
    funds_db = tmp_path / "funds_database.json"
    funds_db.write_text(json.dumps({"funds_database": [
        make_fund("SUSTAINABILITY", 3, 5.0, 10.0, "IE1"),
        make_fund("TECHNOLOGY", 6, 20.0, 40.0, "IE2"),
    ]}), encoding="utf-8")

    loader = QuestionnaireLoader(str(schema))
    # The loader resolves the funds DB from fixed container/cwd locations;
    # point it at the fixture explicitly (local runs have no root DB file).
    loader._funds_db_path = str(funds_db)
    assert loader._apply_dynamic_options()

    section = loader.get_section_by_id("preferred_themes")
    by_value = {o["value"]: o for o in section["options"]}
    assert by_value["sustainability"]["in_band"]["DEFENSIVE"] == 1
    assert by_value["technology"]["in_band"]["DEFENSIVE"] == 0
    assert by_value["technology"]["in_band"]["OPPORTUNITY"] == 1
    # Unbacked canonical themes surface as all-zero counts, not as gaps.
    assert by_value["megatrends"]["in_band"] == {
        "DEFENSIVE": 0, "BALANCED": 0, "OPPORTUNITY": 0
    }


def test_served_questionnaire_survives_translation(tmp_path):
    schema = tmp_path / "preferences_schema.json"
    schema.write_text(json.dumps(MINIMAL_SCHEMA), encoding="utf-8")
    funds_db = tmp_path / "funds_database.json"
    funds_db.write_text(json.dumps({"funds_database": [
        make_fund("SUSTAINABILITY", 3, 5.0, 10.0, "IE1"),
    ]}), encoding="utf-8")

    loader = QuestionnaireLoader(str(schema))
    loader._funds_db_path = str(funds_db)
    loader._apply_dynamic_options()

    translated = loader.get_questionnaire(language="de")
    section = next(s for s in translated["sections"] if s["id"] == "preferred_themes")
    by_value = {o["value"]: o for o in section["options"]}
    assert by_value["sustainability"]["in_band"]["DEFENSIVE"] == 1


# --- engine regression: shared bands keep the backstop identical ---------------

@pytest.mark.parametrize("profile", ["DEFENSIVE", "BALANCED", "OPPORTUNITY", "GARBAGE"])
def test_engine_band_delegation(profile):
    engine = DecisionEngine()
    band = engine._risk_band_for_profile(profile)
    assert band == risk_bands.risk_band_for_profile(profile)


def test_engine_fund_in_risk_band_matches_shared_module(funds):
    engine = DecisionEngine()
    for profile in ("DEFENSIVE", "BALANCED", "OPPORTUNITY"):
        band = risk_bands.risk_band_for_profile(profile)
        for fund in funds:
            assert engine._fund_in_risk_band(fund, band) == risk_bands.fund_in_risk_band(fund, band)


def test_band_values_unchanged():
    # Slide 8 values — frozen on purpose; a change here is a spec decision.
    assert risk_bands.RISK_BANDS["DEFENSIVE"] == {
        "srri_min": 1, "srri_max": 3, "vol_max": 8.0, "vol_min": None, "mdd_max": 15.0,
    }
    assert risk_bands.RISK_BANDS["BALANCED"] == {
        "srri_min": 2, "srri_max": 5, "vol_max": 15.0, "vol_min": 5.0, "mdd_max": 30.0,
    }
    assert risk_bands.RISK_BANDS["OPPORTUNITY"] == {
        "srri_min": 4, "srri_max": 7, "vol_max": None, "vol_min": 10.0, "mdd_max": 50.0,
    }
