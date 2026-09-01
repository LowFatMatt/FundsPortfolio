"""Unit tests for the Phase 2 config space."""

from funds_portfolio.eval.config_space import (
    BOOST_KEYS,
    DEFAULT_BOOST_GRID,
    LIVE_BOOSTS,
    SPEC_BOOSTS,
    baseline_configs,
    boost_config_id,
    build_boost_configs,
)


def test_default_grid_brackets_live_values():
    # The default grid must contain every live boost value so the status quo
    # is explored, not just diffed against from outside the grid.
    for value in LIVE_BOOSTS.values():
        assert value in DEFAULT_BOOST_GRID


def test_default_config_count_with_collapsed_spec_baseline():
    configs = build_boost_configs()  # default grid (7 values)
    # 7^4 grid combos; live is ON the grid (deduped). Post-v3.1 the spec
    # values equal the engine defaults, so no separate spec config is added.
    assert len(configs) == 7**4


def test_baselines_present_and_flagged():
    configs = build_boost_configs()
    by_kind = {c["baseline_kind"]: c for c in configs if c["baseline_kind"]}
    # Spec == live since v3.1 → the spec baseline collapses into "live".
    assert set(by_kind) == {"live"}
    assert by_kind["live"]["boost_elevators"] == LIVE_BOOSTS
    assert by_kind["live"]["is_baseline"] is True


def test_engine_kwargs_ready_for_decision_engine():
    configs = build_boost_configs([0, 5])
    for c in configs:
        assert set(c["boost_elevators"]) == set(BOOST_KEYS)
        assert c["engine_kwargs"] == {"boost_elevators": c["boost_elevators"]}


def test_tiny_grid_count_with_baselines():
    # grid {0,5}: 16 combos; live (45/45/2/2) not on grid -> +1; spec equals
    # live since v3.1 -> no additional config.
    configs = build_boost_configs([0, 5])
    assert len(configs) == 16 + 1
    # excluding baselines shrinks to grid-only count
    cfg = build_boost_configs([0, 5], include_live=False, include_spec=False)
    assert len(cfg) == 16


def test_config_id_is_deterministic():
    boosts = {"ETF": 5.0, "ESG": 10.0, "Region": 20.0, "Theme": 30.0}
    assert boost_config_id(boosts) == "boost_5_10_20_30"
    configs = build_boost_configs([0, 5])
    ids = [c["config_id"] for c in configs]
    assert len(ids) == len(set(ids))


def test_baseline_configs_helper():
    base = baseline_configs()
    assert {c["baseline_kind"] for c in base} == {"live"}


# --- drift guards: eval baselines must mirror the engine / the spec ----------


def test_live_boosts_mirror_engine():
    """LIVE is derived from the engine import — assert it stays that way."""
    from funds_portfolio.portfolio.decision_engine import BOOST_ELEVATORS

    assert LIVE_BOOSTS == dict(BOOST_ELEVATORS)


def test_engine_implements_spec_v3_1_boosts():
    """The engine defaults must equal the spec v3.1 Step 6 table.

    If this fails, either the engine or the spec changed unilaterally —
    reconcile FUND_SELECTION_LOGIC_SPEC_V3.md Step 6 with
    decision_engine.BOOST_ELEVATORS (a spec change is a deliberate decision).
    """
    from funds_portfolio.portfolio.decision_engine import BOOST_ELEVATORS

    assert (
        dict(BOOST_ELEVATORS)
        == SPEC_BOOSTS
        == {
            "ETF": 45.0,
            "ESG": 45.0,
            "Region": 2.0,
            "Theme": 2.0,
        }
    )
