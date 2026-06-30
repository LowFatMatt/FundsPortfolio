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


def test_default_config_count_includes_spec_baseline():
    configs = build_boost_configs()  # default grid
    # 6^4 grid combos, live is on the grid (deduped), spec (Theme=3) is added.
    assert len(configs) == 6**4 + 1


def test_baselines_present_and_flagged():
    configs = build_boost_configs()
    by_kind = {c["baseline_kind"]: c for c in configs if c["baseline_kind"]}
    assert set(by_kind) == {"live", "spec"}
    assert by_kind["live"]["boost_elevators"] == LIVE_BOOSTS
    assert by_kind["spec"]["boost_elevators"] == SPEC_BOOSTS
    assert by_kind["live"]["is_baseline"] is True


def test_engine_kwargs_ready_for_decision_engine():
    configs = build_boost_configs([0, 5])
    for c in configs:
        assert set(c["boost_elevators"]) == set(BOOST_KEYS)
        assert c["engine_kwargs"] == {"boost_elevators": c["boost_elevators"]}


def test_tiny_grid_count_with_baselines():
    # grid {0,5}: 16 combos; live (20s/30/45) not on grid -> +1; spec (3s) -> +1
    configs = build_boost_configs([0, 5])
    assert len(configs) == 16 + 2
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
    assert {c["baseline_kind"] for c in base} == {"live", "spec"}
