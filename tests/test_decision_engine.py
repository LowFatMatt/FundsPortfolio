"""Tests for decision engine preference filtering"""

from funds_portfolio.portfolio.decision_engine import DecisionEngine


def _base_answers():
    return {
        "investment_goal": "retirement",
        "investment_duration": "20_plus_years",
        "monthly_savings": "300_500",
        "investment_knowledge": "experienced",
        "risk_approach": "moderate",
        "loss_tolerance": "high_loss_tolerance",
        "esg_preference": "no_requirement",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": [],
    }


def test_etf_only_filter():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=2)
    answers = _base_answers()
    answers["etf_preference"] = "etf_only"

    funds = [
        {
            "isin": "F1",
            "name": "ETF One",
            "provider": "A",
            "asset_class": "equity",
            "region": "europe",
            "theme": "sustainability",
            "risk_level": 4,
            "srri": 5,
            "yearly_fee": 0.2,
            "esg_label": "HIGH",
            "is_etf": True,
        },
        {
            "isin": "F2",
            "name": "Mutual",
            "provider": "B",
            "asset_class": "bond",
            "region": "global",
            "theme": "none",
            "risk_level": 2,
            "srri": 2,
            "yearly_fee": 0.1,
            "esg_label": "LOW",
            "is_etf": False,
        },
    ]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert recs, "Should produce recommendations"
    assert all(r.get("is_etf") is True for r in recs), (
        "ETF-only should filter out non-ETFs"
    )


def test_esg_basic_filter_excludes_low():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=2)
    answers = _base_answers()
    answers["esg_preference"] = "esg_basic"

    funds = [
        {
            "isin": "F1",
            "name": "High ESG",
            "provider": "A",
            "asset_class": "equity",
            "region": "europe",
            "theme": "sustainability",
            "risk_level": 4,
            "srri": 5,
            "yearly_fee": 0.2,
            "esg_label": "HIGH",
            "is_etf": True,
        },
        {
            "isin": "F2",
            "name": "Low ESG",
            "provider": "B",
            "asset_class": "bond",
            "region": "global",
            "theme": "none",
            "risk_level": 2,
            "srri": 2,
            "yearly_fee": 0.1,
            "esg_label": "LOW",
            "is_etf": True,
        },
    ]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert recs, "Should produce recommendations"
    assert all(r.get("esg_label", "HIGH") != "LOW" for r in recs)


def test_preferred_region_boost_influences_selection():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    answers = _base_answers()
    answers["preferred_regions"] = ["europe"]

    funds = [
        {
            "isin": "F1",
            "name": "EU Fund",
            "provider": "A",
            "asset_class": "equity",
            "region": "europe",
            "theme": "none",
            "risk_level": 4,
            "srri": 4,
            "yearly_fee": 0.2,
            "esg_label": "MEDIUM",
            "is_etf": True,
        },
        {
            "isin": "F2",
            "name": "NA Fund",
            "provider": "A",
            "asset_class": "equity",
            "region": "north_america",
            "theme": "none",
            "risk_level": 4,
            "srri": 4,
            "yearly_fee": 0.2,
            "esg_label": "MEDIUM",
            "is_etf": True,
        },
    ]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert len(recs) == 1
    assert recs[0]["isin"] == "F1", "Preferred region should be boosted in selection"
