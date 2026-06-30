"""Unit tests for the per-portfolio metrics.

Uses synthetic result dicts (same shape as DecisionEngine.recommend output) so
the arithmetic can be checked by hand. The main case mirrors the
port_20260624 Theme-30 boost-hijack pattern: a low-base fund selected via a
Theme boost while a higher-base fund is left out.
"""

import pytest

from funds_portfolio.eval.metrics import compute_metrics


def _synthetic_result():
    recommendations = [
        {
            "isin": "A",
            "name": "A",
            "allocation_percent": 30,
            "region": "north_america",
            "theme": "NONE",
            "is_etf": True,
            "esg_label": "SFDR_ARTICLE_8",
            "provider": "Deka",
            "asset_class": "equity",
            "core_satellite_class": "core",
        },
        {
            "isin": "B",
            "name": "B",
            "allocation_percent": 25,
            "region": "north_america",
            "theme": "NONE",
            "is_etf": True,
            "esg_label": None,
            "provider": "Amundi",
            "asset_class": "equity",
            "core_satellite_class": "core",
        },
        {
            "isin": "C",
            "name": "C",
            "allocation_percent": 20,
            "region": "global",
            "theme": "NONE",
            "is_etf": True,
            "esg_label": "SFDR_ARTICLE_8",
            "provider": "Helaba",
            "asset_class": "equity",
            "core_satellite_class": "core",
        },
        {
            "isin": "D",
            "name": "D",
            "allocation_percent": 15,
            "region": "global",
            "theme": "ai_robotics",
            "is_etf": False,
            "esg_label": None,
            "provider": "Deka",
            "asset_class": "equity",
            "core_satellite_class": "satellite",
        },
        {
            "isin": "E",
            "name": "E",
            "allocation_percent": 10,
            "region": "global",
            "theme": "ai_robotics",
            "is_etf": True,
            "esg_label": "SFDR_ARTICLE_8",
            "provider": "Deka",
            "asset_class": "mixed",
            "core_satellite_class": "satellite",
        },
    ]
    portfolio_metrics = {
        "risk_profile": "OPPORTUNITY",
        "srri_proxy": 6,
        "weighted_fee": 0.5,
        "etf_share": 0.85,
        "region_exposures": {"north_america": 0.55, "global": 0.45},
        "theme_exposures": {"NONE": 0.75, "ai_robotics": 0.25},
    }
    candidates = [
        {
            "isin": "A",
            "base": 83.04,
            "boosts": {"ETF": 20.0, "ESG": 20.0},
            "final": 123.04,
        },
        {
            "isin": "B",
            "base": 82.25,
            "boosts": {"ETF": 20.0, "Region": 30.0},
            "final": 132.25,
        },
        {
            "isin": "C",
            "base": 92.10,
            "boosts": {"ETF": 20.0, "ESG": 20.0},
            "final": 132.10,
        },
        {
            "isin": "X",
            "base": 51.66,
            "boosts": {"ETF": 20.0, "ESG": 20.0, "Region": 30.0},
            "final": 121.66,
        },
        {
            "isin": "E",
            "base": 44.20,
            "boosts": {"ETF": 20.0, "ESG": 20.0, "Theme": 30.0},
            "final": 114.20,
        },
        {"isin": "D", "base": 26.77, "boosts": {"Theme": 30.0}, "final": 56.77},
    ]
    decision_trace = {
        "relaxations": [],
        "used_fallback_risk": False,
        "selection": {"events": [{"type": "thematic_insert"}]},
        "ranking": {"candidates": candidates},
    }
    return {
        "recommendations": recommendations,
        "portfolio_metrics": portfolio_metrics,
        "decision_trace": decision_trace,
        "risk_profile": "OPPORTUNITY",
    }


def test_preference_metrics_hand_computed():
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["north_america"],
        "preferred_themes": ["ai_robotics"],
    }
    m = compute_metrics(answers, _synthetic_result())

    assert m["risk_adherence"] == 1.0
    assert m["esg_match"] == pytest.approx(0.60, abs=1e-3)  # (30+20+10)/100
    assert m["etf_match"] == pytest.approx(0.85, abs=1e-3)  # etf_share
    assert m["region_match"] == pytest.approx(0.55, abs=1e-3)
    assert m["theme_exposure_match"] == pytest.approx(0.25, abs=1e-3)
    assert m["theme_coverage"] == pytest.approx(1.0, abs=1e-3)
    assert m["theme_match"] == pytest.approx(0.625, abs=1e-3)
    assert m["pref_score"] == pytest.approx(0.725, abs=1e-3)


def test_diversification_metrics_hand_computed():
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["north_america"],
        "preferred_themes": ["ai_robotics"],
    }
    m = compute_metrics(answers, _synthetic_result())

    assert m["provider_div"] == pytest.approx(0.6, abs=1e-3)  # 3/5
    assert m["asset_div"] == pytest.approx(0.4, abs=1e-3)  # 2/5
    assert m["region_div"] == pytest.approx(0.4, abs=1e-3)  # 2/5
    assert m["provider_hhi"] == pytest.approx(0.405, abs=1e-3)
    assert m["asset_hhi"] == pytest.approx(0.82, abs=1e-3)
    assert m["region_hhi"] == pytest.approx(0.505, abs=1e-3)
    assert m["satellite_total"] == pytest.approx(0.25, abs=1e-3)
    assert m["satellite_cap_ok"] == 1.0
    assert m["min_alloc_pct"] == pytest.approx(10.0, abs=1e-3)
    assert m["min_allocation_ok"] == 1.0
    assert m["completeness"] == 1.0
    assert m["div_score"] == pytest.approx(0.7333, abs=1e-3)
    assert m["overall"] == pytest.approx(0.7292, abs=1e-3)


def test_boost_hijack_diagnostic_detects_leapfrog():
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["north_america"],
        "preferred_themes": ["ai_robotics"],
    }
    m = compute_metrics(answers, _synthetic_result())

    # base 26.77 selected while base 51.66 was left out -> hijack
    assert m["hijack_detected"] is True
    assert m["hijack_gap"] == pytest.approx(24.89, abs=1e-2)
    # selected mean base (65.672) below pure-quality top-5 mean (70.65) -> negative
    assert m["base_gap_top5"] == pytest.approx(-4.98, abs=1e-2)
    assert m["thematic_inserts"] == 1
    assert 0.0 < m["boost_dependency"] < 1.0


def test_no_preferences_vacuously_satisfied():
    result = _synthetic_result()
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": [],
    }
    m = compute_metrics(answers, result)
    assert m["esg_match"] == 1.0
    assert m["etf_match"] == 1.0
    assert m["region_match"] == 1.0
    assert m["theme_match"] == 1.0
    assert m["regions_active"] is False
    assert m["themes_active"] is False


def test_region_coverage_and_full_match_flags():
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["north_america"],
        "preferred_themes": ["ai_robotics"],
    }
    m = compute_metrics(answers, _synthetic_result())
    # north_america is present among selected funds -> fully covered.
    assert m["region_coverage"] == pytest.approx(1.0, abs=1e-9)
    assert m["region_full_match"] is True
    assert m["theme_full_match"] is True  # ai_robotics is present

    # Asking for a region not in the portfolio drops coverage < 1.0.
    answers2 = dict(answers)
    answers2["preferred_regions"] = ["north_america", "asia"]
    m2 = compute_metrics(answers2, _synthetic_result())
    assert m2["region_coverage"] == pytest.approx(0.5, abs=1e-9)
    assert m2["region_full_match"] is False


def test_full_match_flags_false_when_preference_inactive():
    result = _synthetic_result()
    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": [],
    }
    m = compute_metrics(answers, result)
    # Vacuous 1.0 coverage, but "full match" is False because nothing was asked.
    assert m["region_coverage"] == 1.0
    assert m["theme_coverage"] == 1.0
    assert m["region_full_match"] is False
    assert m["theme_full_match"] is False


def test_empty_portfolio_handling():
    answers = {
        "risk_approach": "conservative",
        "esg_preference": "ART_8_9_ONLY",
        "etf_preference": "etf_only",
        "preferred_regions": ["asia"],
        "preferred_themes": ["water"],
    }
    result = {
        "recommendations": [],
        "portfolio_metrics": {},
        "decision_trace": {"relaxations": [], "used_fallback_risk": True},
        "risk_profile": "DEFENSIVE",
    }
    m = compute_metrics(answers, result)
    assert m["empty"] is True
    assert m["num_funds"] == 0
    assert m["completeness"] == 0.0
    assert m["risk_adherence"] == 0.0  # fallback used
    assert m["esg_match"] == 0.0  # ART required but nothing selected
    assert m["region_match"] == 0.0  # region preferred but nothing matched
