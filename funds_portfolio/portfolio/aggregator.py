"""
Portfolio-level aggregation: weighted NAV series and breakdown rollups.

Policy:
- The portfolio NAV series uses the **intersection** of dates across the
  funds with allocation > 0 (clip to shortest history). Funds whose entire
  history is shorter than the requested window are excluded and listed in
  the response's `notes`.
- All series are rebased to 100 at the first common date.
- Per-fund weights come from the saved Portfolio (allocation_percent / 100).
- No currency conversion (Phase 2 assumes EUR; documented in the plan).

This module is read-only and stateless — pass funds + timeseries in,
get aggregates out.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _nav_pairs(series: Iterable[Dict[str, Any]]) -> List[Tuple[date, float]]:
    out: List[Tuple[date, float]] = []
    for point in series or []:
        d = _parse_date(point.get("d") or point.get("date") or "")
        v = point.get("v") if "v" in point else point.get("nav")
        if d is None or v is None:
            continue
        try:
            out.append((d, float(v)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda p: p[0])
    return out


def _filter_window(
    pairs: List[Tuple[date, float]],
    start: Optional[date],
    end: Optional[date],
) -> List[Tuple[date, float]]:
    if not (start or end):
        return pairs
    return [(d, v) for d, v in pairs if (not start or d >= start) and (not end or d <= end)]


def aggregate_portfolio_nav(
    weighted_series: List[Dict[str, Any]],
    benchmark_series: Optional[List[Dict[str, Any]]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate a list of {isin, weight, nav_series} into a single portfolio
    NAV series (rebased to 100) and a benchmark series (also rebased).

    Returns:
        {
          "as_of": "<iso>",
          "currency": "EUR",
          "portfolio_series": [{"d": "...", "v": 100.0}, ...],
          "benchmark_series": [...] | null,
          "excluded_isins": [...],
          "notes": [...]
        }
    """
    start_d = _parse_date(start) if start else None
    end_d = _parse_date(end) if end else None

    parsed: Dict[str, Tuple[float, List[Tuple[date, float]]]] = {}
    excluded: List[str] = []
    notes: List[str] = []

    total_weight = sum(float(s.get("weight") or 0.0) for s in weighted_series)
    if total_weight <= 0:
        return {
            "as_of": None,
            "currency": "EUR",
            "portfolio_series": [],
            "benchmark_series": None,
            "excluded_isins": [],
            "notes": ["no_allocations"],
        }

    for entry in weighted_series:
        isin = entry.get("isin") or ""
        weight = float(entry.get("weight") or 0.0) / total_weight
        if weight <= 0:
            continue
        pairs = _filter_window(_nav_pairs(entry.get("nav_series") or []), start_d, end_d)
        if not pairs:
            excluded.append(isin)
            continue
        parsed[isin] = (weight, pairs)

    if not parsed:
        return {
            "as_of": None,
            "currency": "EUR",
            "portfolio_series": [],
            "benchmark_series": None,
            "excluded_isins": excluded,
            "notes": ["no_timeseries_data"],
        }

    # Intersection of dates
    date_sets = [set(d for d, _ in pairs) for _, pairs in parsed.values()]
    common_dates = sorted(set.intersection(*date_sets)) if date_sets else []
    if not common_dates:
        return {
            "as_of": None,
            "currency": "EUR",
            "portfolio_series": [],
            "benchmark_series": None,
            "excluded_isins": excluded,
            "notes": ["no_common_dates"],
        }

    if excluded:
        notes.append("clipped_to_shortest_history")

    # Rebase each fund to 100 at the first common date, then weight-sum
    portfolio_series: List[Dict[str, Any]] = []
    rebase_map: Dict[str, float] = {}
    re_weight_total = 0.0
    re_weights: Dict[str, float] = {}
    for isin, (weight, pairs) in parsed.items():
        nav_by_date = dict(pairs)
        first_nav = nav_by_date.get(common_dates[0])
        if not first_nav:
            continue
        rebase_map[isin] = first_nav
        re_weights[isin] = weight
        re_weight_total += weight

    if re_weight_total <= 0:
        return {
            "as_of": None,
            "currency": "EUR",
            "portfolio_series": [],
            "benchmark_series": None,
            "excluded_isins": excluded,
            "notes": ["rebase_failed"],
        }

    # Re-normalise weights after dropping anyone with missing first NAV
    for isin in list(re_weights.keys()):
        re_weights[isin] = re_weights[isin] / re_weight_total

    for d in common_dates:
        v = 0.0
        for isin, (weight, pairs) in parsed.items():
            if isin not in re_weights:
                continue
            nav_by_date = dict(pairs)
            nav = nav_by_date.get(d)
            if nav is None:
                v = None  # type: ignore[assignment]
                break
            v += re_weights[isin] * (nav / rebase_map[isin]) * 100.0
        if v is not None:
            portfolio_series.append({"d": d.isoformat(), "v": round(v, 4)})

    benchmark_out: Optional[List[Dict[str, Any]]] = None
    if benchmark_series:
        b_pairs = _filter_window(_nav_pairs(benchmark_series), start_d, end_d)
        if b_pairs:
            base = b_pairs[0][1]
            if base:
                benchmark_out = [
                    {"d": d.isoformat(), "v": round(v / base * 100.0, 4)}
                    for d, v in b_pairs
                ]

    return {
        "as_of": common_dates[-1].isoformat() if common_dates else None,
        "currency": "EUR",
        "portfolio_series": portfolio_series,
        "benchmark_series": benchmark_out,
        "excluded_isins": excluded,
        "notes": notes,
    }


def aggregate_breakdowns(
    recommendations: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """
    Roll up per-fund asset_class_breakdown and region_breakdown into
    portfolio-weighted aggregates. Falls back to the dominant `asset_class` /
    `region` strings when a fund has no breakdown — that fund's full weight
    goes into the single bucket.

    Returns:
        {"asset_class": {"equity": 0.65, "bond": 0.20, ...},
         "region":      {"global": 0.55, "europe": 0.25, ...}}
    """
    asset_totals: Dict[str, float] = {}
    region_totals: Dict[str, float] = {}
    weight_total = 0.0

    for rec in recommendations:
        weight = float(rec.get("allocation_percent") or 0.0) / 100.0
        if weight <= 0:
            continue
        weight_total += weight

        ac_breakdown = rec.get("asset_class_breakdown") or {}
        if ac_breakdown:
            for k, v in ac_breakdown.items():
                asset_totals[k] = asset_totals.get(k, 0.0) + weight * float(v or 0.0)
        else:
            k = (rec.get("asset_class") or "other").lower()
            asset_totals[k] = asset_totals.get(k, 0.0) + weight

        r_breakdown = rec.get("region_breakdown") or {}
        if r_breakdown:
            for k, v in r_breakdown.items():
                region_totals[k] = region_totals.get(k, 0.0) + weight * float(v or 0.0)
        else:
            k = (rec.get("region") or "unknown").lower()
            region_totals[k] = region_totals.get(k, 0.0) + weight

    def _norm(totals: Dict[str, float]) -> Dict[str, float]:
        if weight_total <= 0:
            return totals
        return {k: round(v / weight_total, 4) for k, v in totals.items()}

    return {
        "asset_class": _norm(asset_totals),
        "region": _norm(region_totals),
    }
