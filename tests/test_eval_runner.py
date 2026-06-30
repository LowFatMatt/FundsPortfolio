"""Unit tests for the in-process runner over a tiny synthetic fund universe."""

import json

import pytest

from funds_portfolio.eval.answer_grid import build_answer_grid, cap_grid
from funds_portfolio.eval.config_space import build_boost_configs
from funds_portfolio.eval.ranking import add_diff_vs_live, rank_configs
from funds_portfolio.eval.runner import run_grid, run_sweep


def _fund(isin, region, theme, **overrides):
    base = {
        "isin": isin,
        "name": f"Fund {isin}",
        "provider": f"Prov {isin[0]}",
        "asset_class": "equity",
        "region": region,
        "theme": theme,
        "esg_label": None,
        "is_etf": True,
        "risk_level": 4,
        "srri": 4,
        "volatility": 12.0,
        "sharpe_ratio": 1.2,
        "max_drawdown": 18.0,
        "yearly_fee": 0.3,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def tiny_universe(tmp_path):
    funds = [
        _fund("F1", "global", "NONE", esg_label="SFDR_ARTICLE_8"),
        _fund("F2", "north_america", "NONE", volatility=12.0),
        _fund("F3", "europe", "NONE", srri=2, risk_level=2, volatility=3.0,
              max_drawdown=5.0, asset_class="bond", is_etf=False, esg_label="SFDR_ARTICLE_8"),
        _fund("F4", "global", "ai_robotics", volatility=14.0, is_etf=False),
        _fund("F5", "global", "energy", volatility=11.0, esg_label="SFDR_ARTICLE_8"),
        _fund("F6", "asia", "NONE", volatility=13.0),
    ]
    path = tmp_path / "funds_database.json"
    path.write_text(json.dumps({"funds_database": funds}), encoding="utf-8")
    return str(path)


def test_runner_returns_one_record_per_answer(tiny_universe):
    grid = cap_grid(build_answer_grid(max_regions=1, max_themes=1), 12)
    records = run_grid(grid, universe_path=tiny_universe, workers=1, progress=False)
    assert len(records) == len(grid)
    first = records[0]
    for key in (
        "answer_id", "risk_approach", "esg_preference", "etf_preference",
        "preferred_regions", "preferred_themes", "n_regions", "n_themes",
        "pref_score", "div_score", "overall", "num_funds",
    ):
        assert key in first


def test_runner_is_reproducible(tiny_universe):
    grid = cap_grid(build_answer_grid(max_regions=1, max_themes=1), 10)
    a = run_grid(grid, universe_path=tiny_universe, workers=1, progress=False)
    b = run_grid(grid, universe_path=tiny_universe, workers=1, progress=False)
    assert a == b


def test_runner_produces_valid_fund_counts(tiny_universe):
    grid = cap_grid(build_answer_grid(max_regions=1, max_themes=1), 12)
    records = run_grid(grid, universe_path=tiny_universe, workers=1, progress=False)
    for r in records:
        assert 0 <= r["num_funds"] <= 5
        assert 0.0 <= r["overall"] <= 1.0


def test_sweep_returns_one_stat_per_config_and_is_deterministic(tiny_universe):
    grid = cap_grid(build_answer_grid(max_regions=1, max_themes=1), 8)
    configs = build_boost_configs([0, 5, 20])  # includes live + spec baselines
    stats_a = run_sweep(grid, configs, universe_path=tiny_universe, workers=1, progress=False)
    stats_b = run_sweep(grid, configs, universe_path=tiny_universe, workers=1, progress=False)
    assert len(stats_a) == len(configs)
    # Same per-config means on re-run (deterministic).
    for a, b in zip(stats_a, stats_b):
        assert a["config_id"] == b["config_id"]
        assert a["overall_mean"] == b["overall_mean"]
    # Required output keys present.
    for s in stats_a:
        assert {"config_id", "boost_elevators", "n", "overall_mean",
                "pref_score_mean", "div_score_mean", "pct_hijack"} <= set(s)


def test_sweep_ranks_and_diffs_against_live(tiny_universe):
    grid = cap_grid(build_answer_grid(max_regions=1, max_themes=1), 8)
    configs = build_boost_configs([0, 5, 20])
    stats = run_sweep(grid, configs, universe_path=tiny_universe, workers=1, progress=False)
    add_diff_vs_live(stats)
    ranked = rank_configs(stats)
    assert ranked[0]["rank"] == 1
    # live baseline carries a diff_vs_live of all zeros against itself
    live = next(s for s in ranked if s["baseline_kind"] == "live")
    assert all(abs(v) < 1e-9 for v in live["diff_vs_live"].values())
