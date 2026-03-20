"""Tests for DecisionEngine preference behavior and explainability."""

from funds_portfolio.portfolio.decision_engine import DecisionEngine


def _fund(
    *,
    isin: str,
    name: str,
    srri: int,
    yearly_fee: float,
    is_etf: bool,
    esg_article_9: bool = False,
    esg_article_8: bool = False,
    esg_label: str = "LOW",
    region: str = "global",
    theme: str = "none",
    provider: str = "provider-a",
    asset_class: str = "equity",
    sharpe_ratio: float = 1.0,
):
    return {
        "isin": isin,
        "name": name,
        "srri": srri,
        "yearly_fee": yearly_fee,
        "is_etf": is_etf,
        "esg_article_9": esg_article_9,
        "esg_article_8": esg_article_8,
        "esg_label": esg_label,
        "region": region,
        "theme": theme,
        "provider": provider,
        "asset_class": asset_class,
        "sharpe_ratio": sharpe_ratio,
    }


def _base_answers():
    return {
        "risk_approach": "moderate",
        "loss_tolerance": "low_loss_tolerance",
        "esg_preference": "no_requirement",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["none"],
    }


def test_etf_only_filter():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(isin="AAA", name="ETF Fund", srri=4, yearly_fee=0.2, is_etf=True),
        _fund(isin="BBB", name="Non-ETF Fund", srri=4, yearly_fee=0.2, is_etf=False),
    ]
    answers = _base_answers()
    answers["etf_preference"] = "etf_only"

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    assert recs
    assert all(r.get("is_etf") for r in recs)


def test_esg_filter_required():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(
            isin="AAA",
            name="ESG Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            esg_article_9=True,
            esg_label="HIGH",
        ),
        _fund(
            isin="BBB",
            name="Non-ESG Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            esg_label="LOW",
        ),
    ]
    answers = _base_answers()
    answers["esg_preference"] = "esg_enhanced"

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    assert recs
    assert all(r.get("isin") == "AAA" for r in recs)


def test_region_preference_boost_selects_matching_fund():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(
            isin="AAA",
            name="Global Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            region="global",
            provider="provider-a",
        ),
        _fund(
            isin="BBB",
            name="Europe Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            region="europe",
            provider="provider-b",
        ),
    ]
    answers = _base_answers()
    answers["preferred_regions"] = ["europe"]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    assert recs
    assert recs[0]["isin"] == "BBB"


def test_theme_preference_boost_selects_matching_fund():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(
            isin="AAA",
            name="Core Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            theme="none",
            provider="provider-a",
        ),
        _fund(
            isin="BBB",
            name="Clean Energy Fund",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            theme="clean_energy",
            provider="provider-b",
        ),
    ]
    answers = _base_answers()
    answers["preferred_themes"] = ["clean_energy"]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    assert recs
    assert recs[0]["isin"] == "BBB"


def test_explainability_payload_shape():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(isin="AAA", name="ETF Fund", srri=4, yearly_fee=0.2, is_etf=True),
    ]
    answers = _base_answers()

    result = engine.recommend(answers, funds)

    assert "explanations" in result
    assert "summary" in result["explanations"]
    assert isinstance(result["explanations"]["summary"], str)
    assert "per_fund" in result["explanations"]
    assert "AAA" in result["explanations"]["per_fund"]
    assert isinstance(result["explanations"]["per_fund"]["AAA"], list)

    assert "decision_trace" in result
    assert "filters" in result["decision_trace"]
    assert "relaxations" in result["decision_trace"]
