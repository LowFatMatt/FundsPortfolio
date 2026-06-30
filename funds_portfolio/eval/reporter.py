"""Reporting for the eval harness.

Two layers:
- Phase 1 (single config): ``aggregate`` over per-answer records -> CSV/JSON/markdown.
- Phase 2 (sweep): a streaming ``ConfigAccumulator`` so per-(answer,config)
  pairs never need to be held in memory, plus per-config CSV / markdown writers.

The accumulator tracks running sum / min / max / count for every numeric
metric and the behavioural booleans, mirroring the Phase 1 ``aggregate`` output
per config.
"""

from __future__ import annotations

import csv
import json
import statistics
from typing import Any, Callable, Dict, List, Optional, Sequence

# Metrics aggregated as distributions (mean/min/max) per config.
NUMERIC_METRICS = [
    "pref_score",
    "risk_adherence",
    "esg_match",
    "etf_match",
    "region_match",
    "theme_match",
    "theme_exposure_match",
    "theme_coverage",
    "region_coverage",
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

# Boolean per-answer conditions -> fractions per config.
BOOL_METRICS: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    "pct_complete": lambda r: r.get("num_funds") == 5,
    "pct_empty": lambda r: bool(r.get("empty")),
    "pct_hijack": lambda r: bool(r.get("hijack_detected")),
    "pct_satellite_cap_ok": lambda r: r.get("satellite_cap_ok") == 1.0,
    "pct_min_alloc_ok": lambda r: r.get("min_allocation_ok") == 1.0,
    "pct_risk_clean": lambda r: r.get("risk_adherence") == 1.0,
}


# --------------------------------------------------------------------------- #
# Phase 1: single-config aggregate
# --------------------------------------------------------------------------- #
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


def _fraction(
    records: List[Dict[str, Any]], pred: Callable[[Dict[str, Any]], bool]
) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if pred(r)) / len(records)


def _cond_fraction(
    records: List[Dict[str, Any]],
    active_pred: Callable[[Dict[str, Any]], bool],
    met_pred: Callable[[Dict[str, Any]], bool],
) -> Optional[float]:
    """Fraction of *active* records that satisfy ``met_pred`` (None if no active).

    Used for the theme/region full-match rates, whose denominator is the subset
    of answers that actually expressed that preference.
    """
    active = [r for r in records if active_pred(r)]
    if not active:
        return None
    return sum(1 for r in active if met_pred(r)) / len(active)


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
        "pct_risk_clean": _fraction(records, lambda r: r.get("risk_adherence") == 1.0),
        "pct_theme_full_match": _cond_fraction(
            records,
            lambda r: r.get("themes_active"),
            lambda r: bool(r.get("theme_full_match")),
        ),
        "pct_region_full_match": _cond_fraction(
            records,
            lambda r: r.get("regions_active"),
            lambda r: bool(r.get("region_full_match")),
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
        f"- region_coverage: {_fmt(summary['region_coverage']['mean'])}",
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
        f"- pct_theme_full_match (of theme-active): {_fmt(beh['pct_theme_full_match'])}",
        f"- pct_region_full_match (of region-active): {_fmt(beh['pct_region_full_match'])}",
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


# --------------------------------------------------------------------------- #
# Phase 2: streaming per-config accumulator
# --------------------------------------------------------------------------- #
def new_accumulator(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "config_id": config["config_id"],
        "label": config["label"],
        "boost_elevators": config.get("boost_elevators"),
        "is_baseline": config.get("is_baseline", False),
        "baseline_kind": config.get("baseline_kind"),
        "count": 0,
        "sum": {m: 0.0 for m in NUMERIC_METRICS},
        "cnt": {m: 0 for m in NUMERIC_METRICS},
        "min": {m: None for m in NUMERIC_METRICS},
        "max": {m: None for m in NUMERIC_METRICS},
        "bool_count": {k: 0 for k in BOOL_METRICS},
        "region_active_sum": 0.0,
        "region_active_count": 0,
        "theme_active_sum": 0.0,
        "theme_active_count": 0,
        "theme_coverage_active_sum": 0.0,
        "region_coverage_active_sum": 0.0,
        "theme_full_count": 0,
        "theme_full_sum": 0,
        "region_full_count": 0,
        "region_full_sum": 0,
    }


def accumulate(acc: Dict[str, Any], record: Dict[str, Any]) -> None:
    """Fold one per-answer record into a config accumulator."""
    acc["count"] += 1
    for m in NUMERIC_METRICS:
        v = record.get(m)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        acc["sum"][m] += fv
        acc["cnt"][m] += 1
        if acc["min"][m] is None or fv < acc["min"][m]:
            acc["min"][m] = fv
        if acc["max"][m] is None or fv > acc["max"][m]:
            acc["max"][m] = fv
    for key, pred in BOOL_METRICS.items():
        if pred(record):
            acc["bool_count"][key] += 1
    if record.get("regions_active"):
        acc["region_active_sum"] += float(record.get("region_match") or 0.0)
        acc["region_active_count"] += 1
        acc["region_coverage_active_sum"] += float(record.get("region_coverage") or 0.0)
        acc["region_full_count"] += 1
        if record.get("region_full_match"):
            acc["region_full_sum"] += 1
    if record.get("themes_active"):
        acc["theme_active_sum"] += float(record.get("theme_match") or 0.0)
        acc["theme_active_count"] += 1
        acc["theme_coverage_active_sum"] += float(record.get("theme_coverage") or 0.0)
        acc["theme_full_count"] += 1
        if record.get("theme_full_match"):
            acc["theme_full_sum"] += 1


def finalize(acc: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce an accumulator into a per-config stats dict."""
    out: Dict[str, Any] = {
        "config_id": acc["config_id"],
        "label": acc["label"],
        "boost_elevators": acc["boost_elevators"],
        "is_baseline": acc["is_baseline"],
        "baseline_kind": acc["baseline_kind"],
        "n": acc["count"],
    }
    for m in NUMERIC_METRICS:
        c = acc["cnt"][m]
        out[f"{m}_mean"] = (acc["sum"][m] / c) if c else None
        out[f"{m}_min"] = acc["min"][m]
        out[f"{m}_max"] = acc["max"][m]
    n = acc["count"] or 1
    for key in BOOL_METRICS:
        out[key] = acc["bool_count"][key] / n
    rac = acc["region_active_count"]
    tac = acc["theme_active_count"]
    out["region_match_when_active"] = (acc["region_active_sum"] / rac) if rac else None
    out["theme_match_when_active"] = (acc["theme_active_sum"] / tac) if tac else None
    out["theme_coverage_when_active"] = (
        (acc["theme_coverage_active_sum"] / tac) if tac else None
    )
    out["region_coverage_when_active"] = (
        (acc["region_coverage_active_sum"] / rac) if rac else None
    )
    out["pct_theme_full_match"] = (
        (acc["theme_full_sum"] / acc["theme_full_count"])
        if acc["theme_full_count"]
        else None
    )
    out["pct_region_full_match"] = (
        (acc["region_full_sum"] / acc["region_full_count"])
        if acc["region_full_count"]
        else None
    )
    out["n_region_active"] = rac
    out["n_theme_active"] = tac
    return out


# --------------------------------------------------------------------------- #
# Phase 2: sweep output (expects stats already ranked + diffed by ranking.py)
# --------------------------------------------------------------------------- #
_SWEEP_CSV_COLUMNS = [
    "rank",
    "config_id",
    "label",
    "ETF",
    "ESG",
    "Region",
    "Theme",
    "is_baseline",
    "baseline_kind",
    "pareto_optimal",
    "composite",
    "n",
    "overall_mean",
    "pref_score_mean",
    "div_score_mean",
    "pct_complete",
    "pct_empty",
    "pct_hijack",
    "pct_satellite_cap_ok",
    "pct_min_alloc_ok",
    "base_gap_top5_mean",
    "hijack_gap_mean",
    "boost_dependency_mean",
    "region_match_when_active",
    "theme_match_when_active",
    "theme_coverage_when_active",
    "region_coverage_when_active",
    "pct_theme_full_match",
    "pct_region_full_match",
    "provider_div_mean",
    "distinct_providers_mean",
    "diff_overall",
    "diff_pref_score",
    "diff_div_score",
    "diff_pct_hijack",
    "diff_base_gap_top5",
    "diff_pct_theme_full_match",
    "diff_pct_region_full_match",
]


def _config_row(stat: Dict[str, Any]) -> Dict[str, Any]:
    boosts = stat.get("boost_elevators") or {}
    diff = stat.get("diff_vs_live") or {}
    row: Dict[str, Any] = {
        "rank": stat.get("rank"),
        "config_id": stat.get("config_id"),
        "label": stat.get("label"),
        "ETF": boosts.get("ETF"),
        "ESG": boosts.get("ESG"),
        "Region": boosts.get("Region"),
        "Theme": boosts.get("Theme"),
        "is_baseline": stat.get("is_baseline"),
        "baseline_kind": stat.get("baseline_kind"),
        "pareto_optimal": stat.get("pareto_optimal"),
        "composite": stat.get("composite"),
        "n": stat.get("n"),
        "overall_mean": stat.get("overall_mean"),
        "pref_score_mean": stat.get("pref_score_mean"),
        "div_score_mean": stat.get("div_score_mean"),
        "pct_complete": stat.get("pct_complete"),
        "pct_empty": stat.get("pct_empty"),
        "pct_hijack": stat.get("pct_hijack"),
        "pct_satellite_cap_ok": stat.get("pct_satellite_cap_ok"),
        "pct_min_alloc_ok": stat.get("pct_min_alloc_ok"),
        "base_gap_top5_mean": stat.get("base_gap_top5_mean"),
        "hijack_gap_mean": stat.get("hijack_gap_mean"),
        "boost_dependency_mean": stat.get("boost_dependency_mean"),
        "region_match_when_active": stat.get("region_match_when_active"),
        "theme_match_when_active": stat.get("theme_match_when_active"),
        "theme_coverage_when_active": stat.get("theme_coverage_when_active"),
        "region_coverage_when_active": stat.get("region_coverage_when_active"),
        "pct_theme_full_match": stat.get("pct_theme_full_match"),
        "pct_region_full_match": stat.get("pct_region_full_match"),
        "provider_div_mean": stat.get("provider_div_mean"),
        "distinct_providers_mean": stat.get("distinct_providers_mean"),
        "diff_overall": diff.get("overall"),
        "diff_pref_score": diff.get("pref_score"),
        "diff_div_score": diff.get("div_score"),
        "diff_pct_hijack": diff.get("pct_hijack"),
        "diff_base_gap_top5": diff.get("base_gap_top5"),
        "diff_pct_theme_full_match": diff.get("pct_theme_full_match"),
        "diff_pct_region_full_match": diff.get("pct_region_full_match"),
    }
    return row


def write_configs_csv(stats: List[Dict[str, Any]], path: str) -> None:
    """One row per config, ranked best-first (use after rank_configs)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SWEEP_CSV_COLUMNS)
        writer.writeheader()
        for stat in stats:
            writer.writerow(_config_row(stat))


def write_sweep_markdown(
    stats: List[Dict[str, Any]],
    path: str,
    *,
    n_answers: int = 0,
    pref_weight: float = 0.5,
    div_weight: float = 0.5,
    hijack_penalty: float = 0.0,
) -> None:
    """Render the sweep recommendation: winner, diff vs live, top-10, Pareto."""
    if not stats:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Decision-Engine Sweep\n\n(no configs)\n")
        return

    winner = stats[0]
    live = next((s for s in stats if s.get("baseline_kind") == "live"), None)
    pareto = [s for s in stats if s.get("pareto_optimal")]

    def _g(s, k):
        v = s.get(f"{k}_mean", s.get(k))
        return f"{v:.3f}" if isinstance(v, (int, float)) else "n/a"

    def _d(s, k):
        v = (s.get("diff_vs_live") or {}).get(k)
        return f"{v:+.3f}" if isinstance(v, (int, float)) else "n/a"

    wb = winner["boost_elevators"]
    lines: List[str] = [
        "# Decision-Engine Boost Sweep",
        "",
        f"- Answer sets per config: {n_answers or winner.get('n', '?')}",
        f"- Configs evaluated: {len(stats)}",
        f"- Objective: {pref_weight:.0%} preference + {div_weight:.0%} diversification"
        + (f" - {hijack_penalty:.2f} x pct_hijack" if hijack_penalty else ""),
        f"- Pareto-optimal configs: {len(pareto)}",
        "",
        "## Recommended config (rank 1)",
        f"- boosts: ETF={wb['ETF']:.0f} ESG={wb['ESG']:.0f} "
        f"Region={wb['Region']:.0f} Theme={wb['Theme']:.0f}",
        f"- composite: {_g(winner, 'composite')}  "
        f"(overall {_g(winner, 'overall')}, pref {_g(winner, 'pref_score')}, "
        f"div {_g(winner, 'div_score')})",
        f"- pct_hijack: {_g(winner, 'pct_hijack')}  "
        f"base_gap_top5: {_g(winner, 'base_gap_top5')}",
        f"- region_match (active): {_g(winner, 'region_match_when_active')}  "
        f"theme_coverage: {_g(winner, 'theme_coverage_when_active')}",
        f"- pct_theme_full_match: {_g(winner, 'pct_theme_full_match')}  "
        f"pct_region_full_match: {_g(winner, 'pct_region_full_match')}",
        "",
        "## Diff vs current live config (positive overall = better)",
        f"- overall: {_d(winner, 'overall')}",
        f"- pref_score: {_d(winner, 'pref_score')}",
        f"- div_score: {_d(winner, 'div_score')}",
        f"- pct_hijack: {_d(winner, 'pct_hijack')} (negative = less hijacking)",
        f"- base_gap_top5: {_d(winner, 'base_gap_top5')} (positive = less quality loss)",
        f"- pct_theme_full_match: {_d(winner, 'pct_theme_full_match')} (positive = more themes fully met)",
        f"- pct_region_full_match: {_d(winner, 'pct_region_full_match')} (positive = more regions fully met)",
        "",
        "## Top 10 configs",
        "| rank | ETF | ESG | Reg | Thm | overall | pref | div | pct_hijack | base_gap_top5 | d_overall | d_pct_hijack | pareto |",
        "|------|-----|-----|-----|-----|---------|------|-----|------------|---------------|-----------|--------------|--------|",
    ]
    for s in stats[:10]:
        b = s["boost_elevators"]
        base = (
            "live"
            if s.get("baseline_kind") == "live"
            else ("spec" if s.get("baseline_kind") == "spec" else "")
        )
        tag = (" " + base) if base else ""
        lines.append(
            f"| {s.get('rank')} | {b['ETF']:.0f} | {b['ESG']:.0f} | "
            f"{b['Region']:.0f} | {b['Theme']:.0f} | {_g(s, 'overall')} | "
            f"{_g(s, 'pref_score')} | {_g(s, 'div_score')} | {_g(s, 'pct_hijack')} | "
            f"{_g(s, 'base_gap_top5')} | {_d(s, 'overall')} | {_d(s, 'pct_hijack')} | "
            f"{'yes' if s.get('pareto_optimal') else ''}{tag} |"
        )
    if live is not None:
        lines.append("")
        lines.append(
            f"Live baseline rank: {live.get('rank')} "
            f"(overall {_g(live, 'overall')}, pct_hijack {_g(live, 'pct_hijack')})"
        )
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
