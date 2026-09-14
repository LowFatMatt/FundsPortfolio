"""v4 decision-engine tests: satellite classification & proportional allocation.

Covers spec v4 Steps 8-11 (see FUND_SELECTION_LOGIC_SPEC_V4.md):
- pass/rank-aware core/satellite classification (Step 8)
- proportional elevated-score allocation with core/satellite bands (Step 9)
- 30 % satellite band cap, 10 % floor (Step 10), integer rounding to 100 % (Step 11)

Plus the v4.1 defensive anchor (pass 0, plans/defensive_anchor_balanced.md):
- anchor pool from the pre-risk-band set, DEFENSIVE band + bond label guard
- fixed per-profile budget carve-out, floor/satellite-cap preservation
- graceful skip for zero-budget profiles and empty pools
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
    assert trace["allocation"]["satellite_total_cap"] == 30
    assert trace["allocation"]["risk_profile"] == "BALANCED"

    sat_total = sum(weights[i] for i in ("SAT1", "SAT2", "SAT3"))
    core_total = sum(weights[i] for i in ("CORE1", "CORE2"))
    assert abs(sat_total - 0.30) < 1e-9
    assert abs(core_total - 0.70) < 1e-9
    # Equal scores within a band → equal split within the band.
    assert abs(weights["SAT1"] - 0.10) < 1e-9
    assert abs(weights["CORE1"] - 0.35) < 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_satellite_cap_is_40_percent_for_opportunity():
    """v4.1: OPPORTUNITY resolves a 40 % satellite cap — the same fund setup
    that triggers the 30/70 split under BALANCED yields 40/60 instead."""
    engine = DecisionEngine()
    funds = [
        _fund(isin="CORE1", name="Core 1", provider="p1"),
        _fund(isin="CORE2", name="Core 2", provider="p2"),
    ] + [
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
        "OPPORTUNITY",
        trace=trace,
    )

    assert trace["allocation"]["satellite_cap_applied"] is True
    assert trace["allocation"]["band_logic"] == "two_band"
    assert trace["allocation"]["satellite_total_cap"] == 40
    assert trace["allocation"]["risk_profile"] == "OPPORTUNITY"

    sat_total = sum(weights[i] for i in ("SAT1", "SAT2", "SAT3"))
    core_total = sum(weights[i] for i in ("CORE1", "CORE2"))
    assert abs(sat_total - 0.40) < 1e-9
    assert abs(core_total - 0.60) < 1e-9
    assert abs(weights["SAT1"] - 0.40 / 3.0) < 1e-9
    assert abs(weights["CORE1"] - 0.30) < 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_constructor_overrides_satellite_caps():
    """A caller-supplied satellite_total_caps map overrides the profiles it
    defines; all other profiles keep the shared defaults from risk_bands."""
    engine = DecisionEngine(satellite_total_caps={"BALANCED": 25.0})
    assert engine._satellite_total_caps["BALANCED"] == 25.0
    assert engine._satellite_total_caps["OPPORTUNITY"] == 40.0
    assert engine._satellite_total_caps["DEFENSIVE"] == 30.0


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


def test_floor_does_not_break_satellite_cap():
    """Regression (port_20260908_f7f5cc88): a capped satellite whose band share
    falls below the 10 % floor must be lifted *within its band* — the satellite
    total stays at the 40 % OPPORTUNITY cap instead of leaking to ~41.6 %."""
    engine = DecisionEngine()
    funds = [
        _fund(isin="CORE1", name="Core 1", provider="p1"),
        _fund(isin="CORE2", name="Core 2", provider="p2"),
    ] + [
        _fund(isin=f"SAT{i}", name=f"Sat {i}", theme="DEFENSE", provider=f"p{i+3}")
        for i in (1, 2, 3)
    ]
    for f in funds[:2]:
        f["_selection_pass"] = 2
        f["_rank_position"] = 1
        f["_scores"] = {"final": 92.1}
    for isin, score, rank in (
        ("SAT1", 57.02, 6),
        ("SAT2", 51.71, 7),
        ("SAT3", 26.77, 8),
    ):
        idx = [x["isin"] for x in funds].index(isin)
        funds[idx]["_selection_pass"] = 1
        funds[idx]["_rank_position"] = rank
        funds[idx]["_scores"] = {"final": score}

    trace = {"allocation": {"satellite_cap_applied": False, "funds": []}}
    weights = engine._allocate_weights(
        funds,
        {"preferred_regions": [], "preferred_themes": []},
        "OPPORTUNITY",
        trace=trace,
    )

    assert trace["allocation"]["satellite_cap_applied"] is True
    assert trace["allocation"]["cap_breached_by_floor"] is False
    # The cap survives the floor: satellites stay at exactly 40 %.
    sat_total = sum(weights[i] for i in ("SAT1", "SAT2", "SAT3"))
    assert abs(sat_total - 0.40) < 1e-9
    # Every fund still meets the 10 % floor.
    assert all(w >= 0.10 - 1e-9 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    # The sub-floor satellite sits exactly at the floor; its band peers
    # donated the deficit.
    assert abs(weights["SAT3"] - 0.10) < 1e-9
    assert weights["SAT1"] > weights["SAT2"] > weights["SAT3"]


def test_floor_falls_back_globally_when_band_floors_infeasible():
    """Corner case: 4 satellites × 10 % floor = 40 % > the 30 % BALANCED cap —
    cap and floor cannot both hold; the global fallback runs and the trace
    flags the breach."""
    engine = DecisionEngine()
    funds = [
        _fund(isin="CORE1", name="Core 1", provider="p1"),
    ] + [
        _fund(isin=f"SAT{i}", name=f"Sat {i}", theme="DEFENSE", provider=f"p{i+2}")
        for i in (1, 2, 3, 4)
    ]
    funds[0].update(
        {"_selection_pass": 2, "_rank_position": 1, "_scores": {"final": 200.0}}
    )
    for i, f in enumerate(funds[1:]):
        f["_selection_pass"] = 1
        f["_rank_position"] = 6 + i
        f["_scores"] = {"final": 50.0}

    trace = {"allocation": {"satellite_cap_applied": False, "funds": []}}
    weights = engine._allocate_weights(
        funds,
        {"preferred_regions": [], "preferred_themes": []},
        "BALANCED",
        trace=trace,
    )

    assert trace["allocation"]["satellite_cap_applied"] is True
    assert trace["allocation"]["cap_breached_by_floor"] is True
    # The floor still holds for every fund (it wins in this corner).
    assert all(w >= 0.10 - 1e-9 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-9


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


# ---------------------------------------------------------------------------
# v4.1 — Pass 0 defensive anchor (plans/defensive_anchor_balanced.md)
# ---------------------------------------------------------------------------


def _anchored_universe():
    """5 BALANCED-band equity candidates + 2 bond ballast funds + 1 srri-3
    multi-asset fund that must NOT win the anchor slot (bond-label guard)."""
    funds = [
        _fund(
            isin=f"E{i}",
            name=f"Equity {i}",
            sharpe_ratio=2.0 - 0.1 * i,
            provider=f"q{i}",
        )
        for i in range(1, 6)
    ]
    funds += [
        # Ballast candidates (DEFENSIVE band: srri 1-3, vol <= 8, mdd <= 15).
        _fund(
            isin="BOND1",
            name="Corp bond ETF",
            asset_class="bond",
            srri=2,
            volatility=3.4,
            max_drawdown=2.9,
            sharpe_ratio=0.5,
            provider="b1",
        ),
        _fund(
            isin="BOND2",
            name="Money market ETF",
            asset_class="bond",
            srri=1,
            volatility=0.8,
            max_drawdown=1.7,
            sharpe_ratio=0.4,
            provider="b2",
        ),
        # srri-3 multi-asset (~35-40 % equity): inside the DEFENSIVE band but
        # not a bond → the P3 hybrid guard keeps it out of the anchor pool.
        _fund(
            isin="MA1",
            name="Conservative multi-asset",
            asset_class="mixed",
            srri=3,
            volatility=6.0,
            max_drawdown=9.0,
            sharpe_ratio=1.2,
            provider="b3",
        ),
    ]
    return funds


def test_balanced_selects_defensive_anchor_with_fixed_budget():
    """BALANCED: anchor = top-scored bond of the pool, pinned at exactly 30 %,
    classified core_defensive_anchor; 4 remaining funds share 70 %."""
    engine = DecisionEngine()
    result = engine.recommend(_base_answers(), _anchored_universe())

    tr = result["decision_trace"]
    anchor = tr["anchor"]
    assert anchor["enabled"] is True
    assert anchor["budget_pct"] == 35.0
    assert set(anchor["pool_isins"]) == {"BOND1", "BOND2"}
    assert anchor["selected_isin"] == "BOND1"  # top-scored of the pool

    allocs = _alloc_by_isin(result)
    assert len(result["recommendations"]) == 5  # anchor + 4 pass-2 picks
    assert allocs["BOND1"] == 35
    assert sum(allocs.values()) == 100
    assert all(a >= 10 for a in allocs.values())

    rec = next(r for r in result["recommendations"] if r["isin"] == "BOND1")
    assert rec["core_satellite_class"] == "core"
    assert rec["core_satellite_reason"] == "core_defensive_anchor"
    assert rec["is_defensive_anchor"] is True

    at = tr["allocation"]
    assert at["anchor_isin"] == "BOND1"
    assert at["anchor_budget"] == 35.0
    assert at["anchor_reduced_by_floor"] is False

    assert result["portfolio_metrics"]["defensive_share"] == 0.35

    events = tr["selection"]["events"]
    assert any(
        e.get("type") == "pass0_anchor_select" and e.get("isin") == "BOND1"
        for e in events
    )


def test_anchor_pool_uses_pre_risk_band_set():
    """The ballast funds fail the BALANCED vol_min (5.0) — the risk band filter
    removes them — yet the anchor is still picked: the pool derives from the
    pre-risk-band set, the one deliberate exception to the profile band."""
    engine = DecisionEngine()
    result = engine.recommend(_base_answers(), _anchored_universe())
    tr = result["decision_trace"]

    rb = next(f for f in tr["filters"] if f["name"] == "risk_band")
    assert rb["before"] == 8  # all funds survived ESG/ETF filters
    assert rb["after"] == 6  # BOND1/BOND2 removed by vol_min…
    assert tr["anchor"]["selected_isin"] == "BOND1"  # …but anchor anyway


def test_zero_budget_profiles_skip_anchor():
    """DEFENSIVE and OPPORTUNITY carry a zero anchor budget → pass 0 skipped,
    selection proceeds exactly as before."""
    engine = DecisionEngine()

    aggressive = _base_answers()
    aggressive["risk_approach"] = "aggressive"
    result = engine.recommend(aggressive, _anchored_universe())
    assert result["decision_trace"]["anchor"]["skipped_reason"] == (
        "zero_budget_for_profile"
    )
    assert result["decision_trace"]["allocation"].get("anchor_isin") is None
    assert len(result["recommendations"]) == 5

    conservative = _base_answers()
    conservative["risk_approach"] = "conservative"
    result = engine.recommend(conservative, _anchored_universe())
    assert result["decision_trace"]["anchor"]["enabled"] is False
    # Thin defensive universe (3 of 8 funds) — the portfolio reflects it.
    assert len(result["recommendations"]) == 3


def test_anchor_skips_gracefully_without_bond_candidates():
    """No bond fund in the universe → pool empty → anchor skipped, portfolio
    unchanged (pre-v4.1 behaviour)."""
    engine = DecisionEngine()
    funds = [f for f in _anchored_universe() if f["asset_class"] != "bond"]
    result = engine.recommend(_base_answers(), funds)

    tr = result["decision_trace"]
    assert tr["anchor"]["enabled"] is True
    assert tr["anchor"]["skipped_reason"] == "no_eligible_defensive_bond_fund"
    assert tr["allocation"].get("anchor_isin") is None
    assert len(result["recommendations"]) == 5
    assert result["portfolio_metrics"]["defensive_share"] == 0.0


def test_constructor_overrides_anchor_budgets():
    engine = DecisionEngine(anchor_budgets={"BALANCED": 40.0})
    assert engine._anchor_budgets["BALANCED"] == 40.0
    assert engine._anchor_budgets["DEFENSIVE"] == 0.0
    assert engine._anchor_budgets["OPPORTUNITY"] == 0.0

    result = engine.recommend(_base_answers(), _anchored_universe())
    assert _alloc_by_isin(result)["BOND1"] == 40


def test_anchor_budget_reduced_when_floor_infeasible():
    """An 80 % budget leaves the 4 rest funds unable to carry the 10 % floor
    (4 × 10 % > 20 %) → reduced to the maximum feasible 60 %, flagged."""
    engine = DecisionEngine(anchor_budgets={"BALANCED": 80.0})
    result = engine.recommend(_base_answers(), _anchored_universe())

    at = result["decision_trace"]["allocation"]
    assert at["anchor_reduced_by_floor"] is True
    assert at["anchor_budget"] == 60.0

    allocs = _alloc_by_isin(result)
    assert allocs["BOND1"] == 60
    assert all(a >= 10 for a in allocs.values())
    assert sum(allocs.values()) == 100


def test_anchor_carve_out_preserves_satellite_cap_and_floor():
    """Anchor pinned at 30 %; satellites capped at 30 % of the TOTAL portfolio
    (expressed as 30/70 % of the rest's space); every fund ≥ 10 %."""
    engine = DecisionEngine()
    funds = [
        _fund(
            isin="ANCHOR",
            name="Anchor",
            asset_class="bond",
            srri=2,
            volatility=3.0,
            max_drawdown=3.0,
            provider="b0",
        ),
        _fund(isin="CORE1", name="Core 1", provider="p1"),
        _fund(isin="CORE2", name="Core 2", provider="p2"),
    ] + [
        _fund(isin=f"SAT{i}", name=f"Sat {i}", theme="DEFENSE", provider=f"p{i + 3}")
        for i in (1, 2, 3)
    ]
    funds[0].update(
        {
            "_selection_pass": 0,
            "_rank_position": 1,
            "_anchor": True,
            "_anchor_budget_pct": 30.0,
            "_scores": {"final": 40.0},
        }
    )
    for f in funds[1:3]:
        f["_selection_pass"] = 2
        f["_rank_position"] = 1
        f["_scores"] = {"final": 100.0}
    for i, f in enumerate(funds[3:]):
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
    assert abs(weights["ANCHOR"] - 0.30) < 1e-9
    sat_total = sum(weights[i] for i in ("SAT1", "SAT2", "SAT3"))
    assert abs(sat_total - 0.30) < 1e-9  # cap measured over the whole portfolio
    assert all(w >= 0.10 - 1e-9 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert trace["allocation"]["anchor_isin"] == "ANCHOR"


def test_anchor_budget_sweep_dimension():
    """eval.config_space: the opt-in anchor dimension spans 25/30/35 (+0 as
    pre-v4.1 contrast); only the live budget keeps the baseline flag."""
    from funds_portfolio.eval.config_space import (
        LIVE_ANCHOR_BAL,
        augment_anchor_budgets,
        baseline_configs,
    )

    assert LIVE_ANCHOR_BAL == 35.0
    configs = augment_anchor_budgets(baseline_configs())
    budgets = sorted(
        {c["engine_kwargs"]["anchor_budgets"]["BALANCED"] for c in configs}
    )
    assert budgets == [0.0, 25.0, 30.0, 35.0]

    live = [c for c in configs if c["is_baseline"]]
    assert len(live) == 1
    assert live[0]["engine_kwargs"]["anchor_budgets"]["BALANCED"] == 35.0


def test_ranking_trace_prepends_anchor_row():
    """The anchor lives outside the banded ranking (pre-band pool) — the
    ranking trace still shows it as rank 0 / selected_pass0_anchor so the
    GUI ranking table includes the pass-0 pick."""
    engine = DecisionEngine()
    result = engine.recommend(_base_answers(), _anchored_universe())
    candidates = result["decision_trace"]["ranking"]["candidates"]

    first = candidates[0]
    assert first["status"] == "selected_pass0_anchor"
    assert first["isin"] == "BOND1"
    assert first["rank"] == 0
    assert first["final"] is not None  # pool-normalised score attached
    # Ranked candidates (rank >= 1) follow unchanged.
    assert candidates[1]["rank"] == 1
    assert len({c["isin"] for c in candidates}) == len(candidates)
