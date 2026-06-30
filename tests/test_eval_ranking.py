"""Unit tests for ranking / Pareto / diff logic and the streaming accumulator."""

import pytest

from funds_portfolio.eval.ranking import (
    add_diff_vs_live,
    composite_score,
    pareto_front,
    rank_configs,
)
from funds_portfolio.eval.reporter import accumulate, aggregate, finalize, new_accumulator


def _stat(cid, pref, div, hijack=0.0, base_gap=0.0, kind=None):
    return {
        "config_id": cid,
        "label": cid,
        "boost_elevators": {"ETF": 0.0, "ESG": 0.0, "Region": 0.0, "Theme": 0.0},
        "is_baseline": kind == "live",
        "baseline_kind": kind,
        "n": 100,
        "pref_score_mean": pref,
        "div_score_mean": div,
        "overall_mean": (pref + div) / 2,
        "pct_hijack": hijack,
        "base_gap_top5_mean": base_gap,
        "hijack_gap_mean": 0.0,
        "boost_dependency_mean": 0.0,
        "region_match_when_active": None,
        "theme_match_when_active": None,
        "theme_coverage_when_active": None,
    }


def test_composite_score_is_weighted_average():
    s = _stat("a", pref=0.8, div=0.6)
    assert composite_score(s) == pytest.approx(0.7)
    assert composite_score(s, pref_weight=0.7, div_weight=0.3) == pytest.approx(
        0.7 * 0.8 + 0.3 * 0.6
    )


def test_hijack_penalty_lowers_composite():
    s = _stat("a", pref=0.8, div=0.6, hijack=0.5)
    assert composite_score(s) == pytest.approx(0.7)
    assert composite_score(s, hijack_penalty=0.2) == pytest.approx(0.7 - 0.2 * 0.5)


def test_rank_configs_orders_by_composite():
    stats = [_stat("low", 0.5, 0.5), _stat("high", 0.9, 0.9), _stat("mid", 0.7, 0.7)]
    ranked = rank_configs(stats)
    assert [s["config_id"] for s in ranked] == ["high", "mid", "low"]
    assert ranked[0]["rank"] == 1


def test_pareto_front_finds_non_dominated():
    # b dominates a (>= everywhere, > somewhere); c is non-dominated with b.
    stats = [
        _stat("a", pref=0.5, div=0.5),
        _stat("b", pref=0.9, div=0.9),
        _stat("c", pref=0.95, div=0.4),
    ]
    front = set(pareto_front(stats))
    assert front == {"b", "c"}
    ranked = rank_configs(stats)
    for s in ranked:
        assert s["pareto_optimal"] == (s["config_id"] in front)


def test_diff_vs_live_annotates_deltas():
    stats = [
        _stat("live", 0.6, 0.6, hijack=0.5, base_gap=-5.0, kind="live"),
        _stat("better", 0.8, 0.8, hijack=0.2, base_gap=-2.0),
    ]
    live = add_diff_vs_live(stats)
    assert live["config_id"] == "live"
    better = next(s for s in stats if s["config_id"] == "better")
    assert better["diff_vs_live"]["overall"] == pytest.approx(0.2)
    assert better["diff_vs_live"]["pct_hijack"] == pytest.approx(-0.3)
    assert better["diff_vs_live"]["base_gap_top5"] == pytest.approx(3.0)


def test_streaming_accumulator_matches_phase1_aggregate():
    # Feeding the same records through the Phase 1 aggregate and the Phase 2
    # streaming accumulator must yield identical means.
    records = [
        {"pref_score": 0.8, "div_score": 0.6, "overall": 0.7, "num_funds": 5,
         "empty": False, "hijack_detected": True, "satellite_cap_ok": 1.0,
         "min_allocation_ok": 1.0, "risk_adherence": 1.0, "regions_active": True,
         "themes_active": False, "region_match": 0.5, "theme_match": 1.0,
         "theme_coverage": 1.0, "region_coverage": 0.5,
         "theme_full_match": False, "region_full_match": False,
         "base_gap_top5": -4.0, "hijack_gap": 10.0,
         "boost_dependency": 0.3, "weighted_fee": 0.4, "srri_proxy": 4,
         "distinct_providers": 3},
        {"pref_score": 0.6, "div_score": 0.8, "overall": 0.7, "num_funds": 5,
         "empty": False, "hijack_detected": False, "satellite_cap_ok": 1.0,
         "min_allocation_ok": 1.0, "risk_adherence": 1.0, "regions_active": True,
         "themes_active": True, "region_match": 0.4, "theme_match": 0.5,
         "theme_coverage": 0.5, "region_coverage": 1.0,
         "theme_full_match": False, "region_full_match": True,
         "base_gap_top5": -6.0, "hijack_gap": 12.0,
         "boost_dependency": 0.4, "weighted_fee": 0.5, "srri_proxy": 5,
         "distinct_providers": 4},
    ]
    summary = aggregate(records)
    config = {"config_id": "c", "label": "c", "boost_elevators": {},
              "is_baseline": False, "baseline_kind": None}
    acc = new_accumulator(config)
    for r in records:
        accumulate(acc, r)
    fin = finalize(acc)

    assert fin["pref_score_mean"] == pytest.approx(summary["pref_score"]["mean"])
    assert fin["div_score_mean"] == pytest.approx(summary["div_score"]["mean"])
    assert fin["pct_hijack"] == pytest.approx(summary["behavior"]["pct_hijack"])
    assert fin["base_gap_top5_mean"] == pytest.approx(summary["base_gap_top5"]["mean"])
    assert fin["region_match_when_active"] == pytest.approx(
        summary["conditional"]["region_match_when_active"]
    )
    # Full-match rates are conditional (denominator = active subset) and must
    # agree between the Phase 1 aggregate and the Phase 2 streaming finalize.
    assert fin["pct_theme_full_match"] == pytest.approx(
        summary["behavior"]["pct_theme_full_match"]
    )
    assert fin["pct_region_full_match"] == pytest.approx(
        summary["behavior"]["pct_region_full_match"]
    )
    assert fin["pct_region_full_match"] == pytest.approx(0.5)  # 1 of 2 region-active
    assert fin["pct_theme_full_match"] == pytest.approx(0.0)   # 0 of 1 theme-active
    assert fin["region_coverage_when_active"] == pytest.approx(0.75)  # (0.5+1.0)/2
