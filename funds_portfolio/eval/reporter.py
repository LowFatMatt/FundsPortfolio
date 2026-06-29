"""Aggregate eval records into CSV / JSON / markdown summaries (single config).

Phase 1 produces per-answer metrics plus an aggregate snapshot of the *current*
config. No ranking or Pareto analysis yet — that arrives with the Phase 2
config sweep.
"""

from __future__ import annotations

import csv
import json
import statistics
from typing import Any, Callable, Dict, List, Sequence

# Metrics aggregated as distributions (mean/median/min/max).
NUMERIC_METRICS = [
    "pref_score",
    "risk_adherence",
    "esg_match",
    "etf_match",
    "region_match",
    "theme_match",
    "theme_exposure_match",
    "theme_coverage",
    "div_score",
    "provider_div",
    "asset_div",
    "region_div",
    "provider_hhi",
    "asset_hhi",
    "region_hhi",
    "satellite_total",
    "satellite_cap_ok",
    "min_allocation_ok",
    "completeness",
    "overall",
    "base_gap_top5",
    "hijack_gap",
    "boost_dependency",
    "thematic_inserts",
    "regional_drops",
    "relaxation_count",
    "num_funds",
    "weighted_fee",
    "srri_proxy",
    "distinct_providers",
    "distinct_asset_classes",
    "distinct_regions",
]


def _dist(values: Sequence[Any]) -> Dict[str, Any]:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"count": 0, "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(vals),
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
    }


def _fraction(records: List[Dict[str, Any]], pred: Callable[[Dict[str, Any]], bool]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if pred(r)) / len(records)


def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-answer records into a single-config summary."""
    summary: Dict[str, Any] = {"n_answers": len(records)}
    for key in NUMERIC_METRICS:
        summary[key] = _dist([r.get(key) for r in records])

    region_active = [r for r in records if r.get("regions_active")]
    theme_active = [r for r in records if r.get("themes_active")]
    summary["conditional"] = {
        "n_region_active": len(region_active),
        "n_theme_active": len(theme_active),
        "region_match_when_active": (
            _dist([r.get("region_match") for r in region_active])["mean"]
            if region_active
            else None
        ),
        "theme_match_when_active": (
            _dist([r.get("theme_match") for r in theme_active])["mean"]
            if theme_active
            else None
        ),
        "theme_coverage_when_active": (
            _dist([r.get("theme_coverage") for r in theme_active])["mean"]
            if theme_active
            else None
        ),
    }
    summary["behavior"] = {
        "pct_complete": _fraction(records, lambda r: r.get("num_funds") == 5),
        "pct_empty": _fraction(records, lambda r: bool(r.get("empty"))),
        "pct_hijack": _fraction(records, lambda r: bool(r.get("hijack_detected"))),
        "pct_satellite_cap_ok": _fraction(
            records, lambda r: r.get("satellite_cap_ok") == 1.0
        ),
        "pct_min_alloc_ok": _fraction(
            records, lambda r: r.get("min_allocation_ok") == 1.0
        ),
        "pct_risk_clean": _fraction(
            records, lambda r: r.get("risk_adherence") == 1.0
        ),
    }
    return summary


def write_csv(records: List[Dict[str, Any]], path: str) -> None:
    """Write per-answer metrics to CSV with a stable, unioned column set."""
    if not records:
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames: List[str] = []
    seen = set()
    for r in records:
        for k in r.keys():
            if k not in seen:
                fieldnames.append(k)
                seen.add(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)


def write_json(summary: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


def write_markdown(
    summary: Dict[str, Any],
    path: str,
    *,
    config_desc: str = "current (in-tree) DecisionEngine config",
) -> None:
    """Render a human-readable single-config summary."""
    cond = summary["conditional"]
    beh = summary["behavior"]
    lines: List[str] = [
        "# Decision-Engine Evaluation Summary",
        "",
        f"- Config: {config_desc}",
        f"- Answer sets evaluated: {summary['n_answers']}",
        "",
        "## Overall (mean)",
        f"- overall: {_fmt(summary['overall']['mean'])}",
        f"- preference: {_fmt(summary['pref_score']['mean'])}",
        f"- diversification: {_fmt(summary['div_score']['mean'])}",
        "",
        "## Preference satisfaction (mean)",
        f"- risk_adherence: {_fmt(summary['risk_adherence']['mean'])}",
        f"- esg_match: {_fmt(summary['esg_match']['mean'])}",
        f"- etf_match: {_fmt(summary['etf_match']['mean'])}",
        f"- region_match: {_fmt(summary['region_match']['mean'])}",
        f"- theme_match: {_fmt(summary['theme_match']['mean'])}",
        f"- theme_coverage: {_fmt(summary['theme_coverage']['mean'])}",
        f"- region_match (when active, n={cond['n_region_active']}): "
        f"{_fmt(cond['region_match_when_active'])}",
        f"- theme_match (when active, n={cond['n_theme_active']}): "
        f"{_fmt(cond['theme_match_when_active'])}",
        "",
        "## Diversification (mean)",
        f"- provider_div: {_fmt(summary['provider_div']['mean'])} "
        f"(distinct providers mean: {_fmt(summary['distinct_providers']['mean'])})",
        f"- asset_div: {_fmt(summary['asset_div']['mean'])}",
        f"- region_div: {_fmt(summary['region_div']['mean'])}",
        f"- provider_hhi: {_fmt(summary['provider_hhi']['mean'])} (lower = more diverse)",
        f"- satellite_total: {_fmt(summary['satellite_total']['mean'])}",
        f"- completeness: {_fmt(summary['completeness']['mean'])}",
        "",
        "## Behaviour (fractions of answer sets)",
        f"- pct_complete (5 funds): {beh['pct_complete']:.3f}",
        f"- pct_empty: {beh['pct_empty']:.3f}",
        f"- pct_hijack: {beh['pct_hijack']:.3f}",
        f"- pct_satellite_cap_ok: {beh['pct_satellite_cap_ok']:.3f}",
        f"- pct_min_alloc_ok: {beh['pct_min_alloc_ok']:.3f}",
        f"- pct_risk_clean: {beh['pct_risk_clean']:.3f}",
        "",
        "## Boost-hijack diagnostic (mean; reported, not in objective)",
        f"- base_gap_top5: {_fmt(summary['base_gap_top5']['mean'])} "
        "(selected mean base minus pure-quality top-5 mean base; negative = "
        "boosts overrode quality)",
        f"- hijack_gap: {_fmt(summary['hijack_gap']['mean'])} "
        "(max non-selected base minus min selected base; >0 = a lower-base "
        "fund leapfrogged a higher-base one via boosts)",
        f"- boost_dependency: {_fmt(summary['boost_dependency']['mean'])} "
        "(boost share of selected funds' final score)",
        f"- thematic_inserts: {_fmt(summary['thematic_inserts']['mean'])}",
        f"- regional_drops: {_fmt(summary['regional_drops']['mean'])}",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
