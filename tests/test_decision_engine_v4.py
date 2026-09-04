"""v4 decision-engine tests: satellite classification & proportional allocation.

Covers spec v4 Steps 8-11 (see FUND_SELECTION_LOGIC_SPEC_V4.md):
- pass/rank-aware core/satellite classification (Step 8)
- proportional elevated-score allocation with core/satellite bands (Step 9)
- 30 % satellite band cap, 10 % floor (Step 10), integer rounding to 100 % (Step 11)
"""

from funds_portfolio.portfolio.decision_engine import DecisionEngine


def _fund(
    *,
    isin: str,
    name: str,
    srri: int = 4,
    yearly_fee: float = 0.2,
    is_etf: bool = True,
    esg_label: str = None,
    region: str = "global",
    theme: str = "none",
    provider: str = "provider-a",
    asset_class: str = "equity",
    sharpe_ratio: float = 1.0,
    volatility: float = 10.0,
    max_drawdown: float = 12.0,
):
    f = {
        "isin": isin,
        "name": name,
        "srri": srri,
        "yearly_fee": yearly_fee,
        "is_etf": is_etf,
        "esg_label": esg_label,
        "region": region,
        "theme": theme,
        "provider": provider,
        "asset_class": asset_class,
        "sharpe_ratio": sharpe_ratio,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
    }
    return f


def _base_answers():
    return {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["none"],
    }


def _class_by_isin(result):
    return {
        r["isin"]: r["core_satellite_class"] for r in result["recommendations"]
    }


def _alloc_by_isin(result):
    return {
        r["isin"]: r["allocation_percent"] for r in result["recommendations"]
    }


# ---------------------------------------------------------------------------
# Step 8 — classification via the full recommend() pipeline
# ---------------------------------------------------------------------------


def _sustainability_universe():
    """6 funds: SUST ranks #1, four plain cores, DEF ranks last (#6)."""
    return [
        _fund(
            isin="SUST",
            name="Sustainable top performer",
            sharpe_ratio=2.0,
            theme="SUSTAINABILITY",
            provider="p1",
        ),
        _fund(isin="C1", name="Core one", sharpe_ratio=1.9, provider="p2"),
        _fund(isin="C2", name="Core two", sharpe_ratio=1.8, provider="p3"),
        _fund(isin="C3", name="Core three", sharpe_ratio=1.7, provider="p4"),
        _fund(isin="C4", name="Core four", sharpe_ratio=1.6, provider="p5"),
        _fund(
            isin="DEF",
            name="Defense niche pick",
            sharpe_ratio=0.5,
            theme="DEFENSE",
            provider="p6",
        ),
    ]


def test_pass1_top_performer_is_core_and_gets_largest_allocation():
    """A sustainability fund ranked #1 and picked in pass 1 is core (it would
    have been selected by quality anyway) and receives the largest allocation."""
    engine = DecisionEngine()
    answers = _base_answers()
    answers["preferred_themes"] = ["sustainability", "defense"]

    result = engine.recommend(answers, _sustainability_universe())
    classes = _class_by_isin(result)
    allocs = _alloc_by_isin(result)

    assert classes["SUST"] == "core"
    assert classes["DEF"] == "satellite"
    assert classes["C1"] == "core"

    # Best performer gets the largest slice — no satellite downgrade.
    assert allocs["SUST"] == max(allocs.values())
    # Coverage-only pick is floored at the 10 % minimum.
    assert allocs["DEF"] == 10

    rec_sust = next(r for r in result["recommendations"] if r["isin"] == "SUST")
    assert rec_sust["core_satellite_reason"] == "core_top_performer"


def test_coverage_only_pick_classified_as_satellite():
    """A pass-1 pick ranked outside the top final_fund_count is a satellite."""
    engine = DecisionEngine()
    answers = _base_answers()
    answers["preferred_themes"] = ["sustainability", "defense"]

    result = engine.recommend(answers, _sustainability_universe())
    rec_def = next(r for r in result["recommendations"] if r["isin"] == "DEF")
    assert rec_def["core_satellite_class"] == "satellite"
    assert rec_def["core_satellite_reason"] == "satellite_coverage_only"

    # Classification is fully traced.
    cls = result["decision_trace"]["classification"]
    by_isin = {f["isin"]: f for f in cls["funds"]}
    assert by_isin["SUST"]["reason"] == "core_top_performer"
    assert by_isin["DEF"]["reason"] == "satellite_coverage_only"
    assert by_isin["DEF"]["rank_position"] == 6


def test_pass2_picks_are_core_quality_selected():
    engine = DecisionEngine()
    answers = _base_answers()
    answers["preferred_themes"] = ["sustainability", "defense"]

    result = engine.recommend(answers, _sustainability_universe())
    cls = result["decision_trace"]["classification"]
    by_isin = {f["isin"]: f for f in cls["funds"]}
    assert by_isin["C1"]["reason"] == "core_quality_selected"
    assert by_isin["C1"]["selection_pass"] == 2


def test_all_cores_when_no_preferences():
    """Without preferences every pick is a pass-2 quality pick → all core,
    single-band allocation (the common no-preference case)."""
    engine = DecisionEngine()
    funds = _sustainability_universe()
    result = engine.recommend(_base_answers(), funds)

    assert all(c == "core" for c in _class_by_isin(result).values())
    assert result["decision_trace"]["allocation"]["band_logic"] == "single_band"
    assert result["decision_trace"]["allocation"]["satellite_cap_applied"] is False


def test_up_to_three_satellites_under_current_config():
    """With max 3 region/theme preferences at most 3 satellites are selected,
    so cores always remain (the all-satellite case cannot occur)."""
    engine = DecisionEngine()
    funds = [
        _fund(isin=f"K{i}", name=f"Core {i}", sharpe_ratio=2.1 - 0.1 * i, provider=f"p{i}")
        for i in range(5)
    ]
    funds += [
        _fund(
            isin="S2", name="Sust niche", sharpe_ratio=1.0,
            theme="SUSTAINABILITY", provider="p6",
        ),
        _fund(
            isin="D2", name="Defense niche", sharpe_ratio=0.9,
            theme="DEFENSE", provider="p7",
        ),
        _fund(
            isin="A2", name="Asia niche", sharpe_ratio=0.8,
            region="asia", provider="p8",
        ),
    ]
    answers = _base_answers()
    answers["preferred_themes"] = ["sustainability", "defense"]
    answers["preferred_regions"] = ["asia"]

    result = engine.recommend(answers, funds)
    classes = list(_class_by_isin(result).values())

    assert classes.count("satellite") == 3
    assert classes.count("core") >= 1  # cores always remain under this config

    allocs = list(_alloc_by_isin(result).values())
    assert all(a >= 10 for a in allocs)
    assert sum(allocs) == 100


# ---------------------------------------------------------------------------
# Steps 9-11 — allocation math (direct, with annotated funds)
# ---------------------------------------------------------------------------


def _annotated(engine_ready_funds):
    """Attach elevated scores / selection context for direct allocation tests."""
    return engine_ready_funds


def test_two_band_allocation_caps_satellites_at_30_percent():
    """3 satellites with high scores would take > 30 % → two bands:
    satellites 30 %, cores 70 %, proportional by score within each band."""
    engine = DecisionEngine()
    funds = [
        # 2 quality cores, score 100 each
        _fund(isin="CORE1", name="Core 1", provider="p1"),
        _fund(isin="CORE2", name="Core 2", provider="p2"),
    ] + [
        # 3 coverage satellites, score 90 each — natural share 270/470 > 30 %
        _fund(isin=f"SAT{i}", name=f"Sat {i}", theme="DEFENSE", provider=f"p{i+3}")
        for i in (1, 2, 3)
    ]
    for f in funds[:2]:
        f["_selection_pass"] = 2
        f["_rank_position"] = 1
        f["_scores"] = {"final": 100.0}
    for i, f in enumerate(funds[2:]):
        f["_selection_pass"] = 1
        f["_rank_position"] = 6 + i
        f["_scores"] = {"final": 90.0}

    trace = {"allocation": {"satellite_cap_applied": False, "funds": []}}
    weights = engine._allocate_weights(
        funds,
        {"preferred_regions": [], "preferred_themes": []},
        "BALANCED",
        trace=trace,
    )

    assert trace["allocation"]["satellite_cap_applied"] is True
    assert trace["allocation"]["band_logic"] == "two_band"

    sat_total = sum(weights[i] for i in ("SAT1", "SAT2", "SAT3"))
    core_total = sum(weights[i] for i in ("CORE1", "CORE2"))
    assert abs(sat_total - 0.30) < 1e-9
    assert abs(core_total - 0.70) < 1e-9
    # Equal scores within a band → equal split within the band.
    assert abs(weights["SAT1"] - 0.10) < 1e-9
    assert abs(weights["CORE1"] - 0.35) < 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_single_band_when_satellites_naturally_below_cap():
    """1 low-ranked satellite takes well under 30 % → no band split; all funds
    share 100 % proportionally to elevated score."""
    engine = DecisionEngine()
    funds = [
        _fund(isin="CORE1", name="Core 1", provider="p1"),
        _fund(isin="CORE2", name="Core 2", provider="p2"),
        _fund(isin="CORE3", name="Core 3", provider="p3"),
        _fund(isin="CORE4", name="Core 4", provider="p4"),
        _fund(isin="SATX", name="Sat X", theme="DEFENSE", provider="p5"),
    ]
    for i, f in enumerate(funds[:4]):
        f["_selection_pass"] = 2
        f["_rank_position"] = 1 + i
        f["_scores"] = {"final": 100.0}
    funds[4].update(
        {"_selection_pass": 1, "_rank_position": 6, "_scores": {"final": 90.0}}
    )

    trace = {"allocation": {"satellite_cap_applied": False, "funds": []}}
    weights = engine._allocate_weights(
        funds,
        {"preferred_regions": [], "preferred_themes": []},
        "BALANCED",
        trace=trace,
    )

    assert trace["allocation"]["satellite_cap_applied"] is False
    assert trace["allocation"]["band_logic"] == "single_band"
    # Purely proportional: satellite gets 90 / 490 of the whole portfolio.
    assert abs(weights["SATX"] - 90.0 / 490.0) < 1e-9
    assert abs(weights["CORE1"] - 100.0 / 490.0) < 1e-9


def test_proportional_within_band_follows_score_order():
    """Within a band, higher elevated score ⇒ higher weight (3:2:1)."""
    engine = DecisionEngine()
    funds = []
    for isin, score in (("A", 300.0), ("B", 200.0), ("C", 100.0)):
        f = _fund(isin=isin, name=isin, provider=f"p{isin}")
        f["_selection_pass"] = 2
        f["_rank_position"] = 1
        f["_scores"] = {"final": score}
        funds.append(f)

    weights = engine._allocate_weights(
        funds, {"preferred_regions": [], "preferred_themes": []}, "BALANCED"
    )

    assert abs(weights["A"] - 0.5) < 1e-9
    assert abs(weights["B"] - 1.0 / 3.0) < 1e-9
    assert abs(weights["C"] - 1.0 / 6.0) < 1e-9


def test_min_allocation_floor_enforced():
    """The water-filling floor lifts sub-10 % funds up to 10 % and reclaims
    the deficit from funds above the floor."""
    engine = DecisionEngine()
    funds = []
    scores = {"A": 100.0, "B": 100.0, "C": 100.0, "D": 100.0, "TINY": 1.0}
    for isin, score in scores.items():
        f = _fund(isin=isin, name=isin, provider=f"p{isin}")
        f["_selection_pass"] = 2
        f["_rank_position"] = 1
        f["_scores"] = {"final": score}
        funds.append(f)

    trace = {"allocation": {"satellite_cap_applied": False, "funds": []}}
    weights = engine._allocate_weights(
        funds,
        {"preferred_regions": [], "preferred_themes": []},
        "BALANCED",
        trace=trace,
    )

    assert all(w >= 0.10 - 1e-9 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert trace["allocation"]["min_allocation_applied"] is True
    # TINY sits exactly at the floor; donors keep proportionality above it.
    assert abs(weights["TINY"] - 0.10) < 1e-9
    assert weights["A"] == weights["B"] == weights["C"] == weights["D"] > 0.10


# ---------------------------------------------------------------------------
# Step 11 — integer rounding
# ---------------------------------------------------------------------------


def test_integer_allocations_sum_to_100():
    engine = DecisionEngine()
    answers = _base_answers()
    answers["preferred_themes"] = ["sustainability", "defense"]

    result = engine.recommend(answers, _sustainability_universe())
    allocs = [r["allocation_percent"] for r in result["recommendations"]]

    assert all(isinstance(a, int) for a in allocs)
    assert sum(allocs) == 100
