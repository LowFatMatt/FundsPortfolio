"""Rank / Pareto / diff logic for the Phase 2 config sweep.

Operates on per-config stats produced by ``reporter.finalize`` (mean / min /
max per metric + behavioural fractions). The objective is preference-satisfaction
+ diversification; a boost-hijack penalty is available but OFF by default
(stays a reported diagnostic unless explicitly turned on).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# Metrics surfaced as ``<name>_mean`` in per-config stats.
_MEAN_METRICS = [
    "pref_score",
    "div_score",
    "overall",
    "base_gap_top5",
    "hijack_gap",
    "boost_dependency",
]
# Metrics stored directly (fractions / conditional means).
_DIRECT_METRICS = [
    "pct_hijack",
    "pct_complete",
    "pct_empty",
    "pct_satellite_cap_ok",
    "pct_min_alloc_ok",
    "region_match_when_active",
    "theme_match_when_active",
    "theme_coverage_when_active",
    "region_coverage_when_active",
    "pct_theme_full_match",
    "pct_region_full_match",
]

_DIFF_KEYS = [
    "overall",
    "pref_score",
    "div_score",
    "pct_hijack",
    "base_gap_top5",
    "region_match_when_active",
    "theme_coverage_when_active",
    "pct_theme_full_match",
    "pct_region_full_match",
]


def _val(stat: Dict[str, Any], key: str) -> Optional[float]:
    """Read a metric whether it is stored as ``<key>_mean`` or directly."""
    mean_key = f"{key}_mean"
    if mean_key in stat and stat[mean_key] is not None:
        return float(stat[mean_key])
    if key in stat and stat[key] is not None:
        return float(stat[key])
    return None


def composite_score(
    stat: Dict[str, Any],
    *,
    pref_weight: float = 0.5,
    div_weight: float = 0.5,
    hijack_penalty: float = 0.0,
) -> float:
    """Weighted preference+diversification score, optionally minus a hijack penalty.

    ``hijack_penalty`` multiplies ``pct_hijack`` (0..1). Default 0 keeps the
    objective pure preference+diversification.
    """
    pref = _val(stat, "pref_score") or 0.0
    div = _val(stat, "div_score") or 0.0
    wsum = pref_weight + div_weight
    base = (pref_weight * pref + div_weight * div) / wsum if wsum else 0.0
    hijack = _val(stat, "pct_hijack") or 0.0
    return base - hijack_penalty * hijack


def pareto_front(
    stats: Sequence[Dict[str, Any]],
    keys: Sequence[str] = ("pref_score", "div_score"),
) -> List[str]:
    """Config_ids on the Pareto front (maximise every key). None values break
    membership (a config missing a key cannot dominate/be compared reliably)."""
    front: List[str] = []
    for i, a in enumerate(stats):
        va = [_val(a, k) for k in keys]
        if any(v is None for v in va):
            continue
        dominated = False
        for j, b in enumerate(stats):
            if i == j:
                continue
            vb = [_val(b, k) for k in keys]
            if any(v is None for v in vb):
                continue
            # b dominates a if b >= a everywhere and strictly > somewhere
            if all(vb[t] >= va[t] for t in range(len(keys))) and any(
                vb[t] > va[t] for t in range(len(keys))
            ):
                dominated = True
                break
        if not dominated:
            front.append(a["config_id"])
    return front


def add_diff_vs_live(stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Annotate each config with deltas vs the live baseline; return the live stat.

    Falls back to the highest-overall config if no live baseline is present.
    """
    live = next((s for s in stats if s.get("baseline_kind") == "live"), None)
    if live is None:
        live = max(stats, key=lambda s: _val(s, "overall") or 0.0) if stats else None
    if live is None:
        return {}
    for s in stats:
        s["diff_vs_live"] = {
            k: (_val(s, k) or 0.0) - (_val(live, k) or 0.0) for k in _DIFF_KEYS
        }
    return live


def rank_configs(
    stats: List[Dict[str, Any]],
    *,
    pref_weight: float = 0.5,
    div_weight: float = 0.5,
    hijack_penalty: float = 0.0,
    pareto_keys: Sequence[str] = ("pref_score", "div_score"),
) -> List[Dict[str, Any]]:
    """Attach composite, rank, and Pareto membership; return sorted (best first)."""
    front = set(pareto_front(stats, pareto_keys))
    for s in stats:
        s["composite"] = composite_score(
            s,
            pref_weight=pref_weight,
            div_weight=div_weight,
            hijack_penalty=hijack_penalty,
        )
        s["pareto_optimal"] = s["config_id"] in front
    ranked = sorted(stats, key=lambda s: s["composite"], reverse=True)
    for idx, s in enumerate(ranked, 1):
        s["rank"] = idx
    return ranked
