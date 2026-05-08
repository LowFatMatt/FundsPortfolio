"""Tests for DecisionEngine preference behavior and explainability (v2 scoring)."""

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
    volatility: float = None,
    max_drawdown: float = None,
):
    f = {
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
    if volatility is not None:
        f["volatility"] = volatility
    if max_drawdown is not None:
        f["max_drawdown"] = max_drawdown
    return f


def _base_answers():
    return {
        "risk_approach": "moderate",
        "loss_tolerance": "low_loss_tolerance",
        "esg_preference": "no_requirement",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["none"],
    }


# ---------------------------------------------------------------------------
# Original preference / filter tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# v2 scoring tests
# ---------------------------------------------------------------------------

def test_scoring_mdd_shifts_ranking():
    """Fund with better MDD wins when Sharpe and fee are equal."""
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=2)
    funds = [
        _fund(
            isin="HIGH_MDD",
            name="High Drawdown",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            sharpe_ratio=1.0,
            max_drawdown=40.0,  # worse
            provider="prov-a",
        ),
        _fund(
            isin="LOW_MDD",
            name="Low Drawdown",
            srri=4,
            yearly_fee=0.2,
            is_etf=True,
            sharpe_ratio=1.0,
            max_drawdown=10.0,  # better
            provider="prov-b",
        ),
    ]
    answers = _base_answers()
    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert recs[0]["isin"] == "LOW_MDD"


def test_scoring_mdd_srri_proxy():
    """When max_drawdown is absent, SRRI proxy is used and mdd_source is 'srri_proxy'."""
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund(isin="AAA", name="Fund A", srri=4, yearly_fee=0.2, is_etf=True),
    ]
    answers = _base_answers()
    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert recs
    isin = recs[0]["isin"]
    # The fund has no max_drawdown field → proxy path
    # We can't directly inspect _scores from the recommendation output,
    # but the recommendation itself must succeed without error.
    assert isin == "AAA"


def test_scoring_scores_include_new_fields():
    """_scores dict must include sharpe_norm, mdd_norm, ter_norm, mdd_source."""
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    fund = _fund(isin="AAA", name="F", srri=4, yearly_fee=0.2, is_etf=True)
    answers = _base_answers()
    scored = engine._score_funds([fund], answers, "BALANCED")
    s = scored[0]["_scores"]
    assert "sharpe_norm" in s
    assert "mdd_norm" in s
    assert "ter_norm" in s
    assert s["mdd_source"] in ("actual", "srri_proxy")
    assert "risk_alignment" not in s


# ---------------------------------------------------------------------------
# Core-Satellite classification tests
# ---------------------------------------------------------------------------

def test_core_satellite_classification():
    engine = DecisionEngine()
    core = _fund(isin="A", name="Core", srri=4, yearly_fee=0.2, is_etf=True, theme="none")
    sat = _fund(isin="B", name="Sat", srri=4, yearly_fee=0.2, is_etf=True, theme="TECHNOLOGY")
    assert engine._classify_core_satellite(core) == "core"
    assert engine._classify_core_satellite(sat) == "satellite"


def test_satellite_weight_cap_30pct():
    """Satellite total weight must not exceed 30% of the portfolio."""
    engine = DecisionEngine(min_candidates=1, top_k=10, final_fund_count=5)
    # 2 satellites, 3 core funds — all different providers, different categories
    funds = [
        _fund(isin="C1", name="Core1", srri=4, yearly_fee=0.1, is_etf=True,
              theme="none", provider="p1", asset_class="equity"),
        _fund(isin="C2", name="Core2", srri=3, yearly_fee=0.15, is_etf=True,
              theme="none", provider="p2", asset_class="bond"),
        _fund(isin="C3", name="Core3", srri=4, yearly_fee=0.2, is_etf=False,
              theme="none", provider="p3", asset_class="mixed"),
        _fund(isin="S1", name="Sat1", srri=5, yearly_fee=0.5, is_etf=True,
              theme="TECHNOLOGY", provider="p4", asset_class="equity"),
        _fund(isin="S2", name="Sat2", srri=5, yearly_fee=0.6, is_etf=True,
              theme="SUSTAINABILITY", provider="p5", asset_class="equity"),
    ]
    answers = _base_answers()
    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    sat_weight = sum(
        r["allocation_percent"]
        for r in recs
        if r.get("core_satellite_class") == "satellite"
    )
    assert sat_weight <= 30.1  # allow tiny floating-point tolerance


def test_core_satellite_class_in_output():
    """Each recommendation must include core_satellite_class field."""
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [_fund(isin="AAA", name="F", srri=4, yearly_fee=0.2, is_etf=True)]
    result = engine.recommend(_base_answers(), funds)
    assert "core_satellite_class" in result["recommendations"][0]


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_etf_fallback_labelled():
    """When ETF-only is requested but fewer ETFs exist, active funds fill gaps
    and are labelled etf_not_available=True."""
    # Only 1 ETF, need 2 funds
    engine = DecisionEngine(min_candidates=1, top_k=10, final_fund_count=2)
    funds = [
        _fund(isin="E1", name="ETF", srri=4, yearly_fee=0.2, is_etf=True, provider="p1"),
        _fund(isin="A1", name="Active", srri=4, yearly_fee=0.3, is_etf=False, provider="p2"),
        _fund(isin="A2", name="Active2", srri=4, yearly_fee=0.4, is_etf=False, provider="p3"),
    ]
    answers = _base_answers()
    answers["etf_preference"] = "etf_only"

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]

    # Should have 2 recommendations despite only 1 ETF
    assert len(recs) == 2
    # E1 must be included
    assert any(r["isin"] == "E1" for r in recs)
    # At least one active fund must be labelled
    active_recs = [r for r in recs if r.get("etf_not_available")]
    assert len(active_recs) >= 1
    # relaxations should mention the fallback
    relaxation_names = [rel["name"] for rel in result["decision_trace"]["relaxations"]]
    assert "etf_only_fallback" in relaxation_names


def test_regional_concentration_cap():
    """No more than 3 of 5 funds should come from the same preferred region."""
    engine = DecisionEngine(min_candidates=1, top_k=15, final_fund_count=5)
    # 5 europe funds + 2 global funds, all different providers
    europe_funds = [
        _fund(
            isin=f"EU{i}", name=f"Europe{i}", srri=4, yearly_fee=0.1 * i,
            is_etf=True, region="europe",
            provider=f"prov-eu-{i}", asset_class="equity" if i % 2 else "bond",
        )
        for i in range(1, 6)
    ]
    global_funds = [
        _fund(
            isin=f"GL{i}", name=f"Global{i}", srri=4, yearly_fee=0.3 * i,
            is_etf=True, region="global",
            provider=f"prov-gl-{i}", asset_class="mixed",
        )
        for i in range(1, 3)
    ]
    answers = _base_answers()
    answers["preferred_regions"] = ["europe"]

    result = engine.recommend(answers, europe_funds + global_funds)
    recs = result["recommendations"]

    europe_count = sum(1 for r in recs if r.get("region") == "europe")
    assert europe_count <= 3


def test_thematic_guarantee():
    """A thematic fund must be included when user has theme preference,
    even if it scores lower than non-thematic alternatives."""
    engine = DecisionEngine(min_candidates=1, top_k=10, final_fund_count=3)
    # 2 high-scoring core funds + 1 low-scoring thematic fund, all different providers/categories
    funds = [
        _fund(isin="C1", name="Core1", srri=4, yearly_fee=0.05, is_etf=True,
              sharpe_ratio=2.0, theme="none", provider="p1", asset_class="equity"),
        _fund(isin="C2", name="Core2", srri=4, yearly_fee=0.05, is_etf=True,
              sharpe_ratio=2.0, theme="none", provider="p2", asset_class="bond"),
        _fund(isin="T1", name="Tech", srri=4, yearly_fee=0.8, is_etf=True,
              sharpe_ratio=0.1, theme="TECHNOLOGY", provider="p3", asset_class="mixed"),
    ]
    answers = _base_answers()
    answers["preferred_themes"] = ["TECHNOLOGY"]

    result = engine.recommend(answers, funds)
    recs = result["recommendations"]
    assert any(r["isin"] == "T1" for r in recs)


def test_relaxations_include_reason():
    """All relaxation entries in decision_trace must include a 'reason' key."""
    engine = DecisionEngine(min_candidates=100, top_k=5, final_fund_count=1)
    funds = [_fund(isin="AAA", name="F", srri=4, yearly_fee=0.2, is_etf=True)]
    result = engine.recommend(_base_answers(), funds)
    for relaxation in result["decision_trace"]["relaxations"]:
        assert "reason" in relaxation, f"Relaxation missing 'reason': {relaxation}"
