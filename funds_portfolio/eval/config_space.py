"""Phase 2 configuration space for the DecisionEngine sweep.

Primary lever: ``BOOST_ELEVATORS`` (ETF/ESG/Region/Theme). The live in-tree
values and the spec values are always emitted as explicit baselines so the
sweep can diff every candidate against the status quo. The default grid
``[0, 5, 10, 20, 30, 45]`` brackets every live value (max is Theme=45).

Secondary knobs (scoring weights, caps, risk bands, tier bounds, satellite
cap, regional tilt) are intentionally NOT materialised here yet — Phase 2
focuses on boosts; they are queued for a later stage if the boost sweep
plateaus.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Sequence

# Canonical boost keys; must match decision_engine.BOOST_ELEVATORS.
BOOST_KEYS = ("ETF", "ESG", "Region", "Theme")

# Live in-tree values (funds_portfolio/portfolio/decision_engine.py).
LIVE_BOOSTS: Dict[str, float] = {
    "ETF": 20.0,
    "ESG": 20.0,
    "Region": 30.0,
    "Theme": 45.0,
}
# Spec values (FUND_SELECTION_LOGIC_SPEC_V2.md, Step 6).
SPEC_BOOSTS: Dict[str, float] = {
    "ETF": 5.0,
    "ESG": 5.0,
    "Region": 3.0,
    "Theme": 3.0,
}

# Brackets every live value (max live = Theme 45).
DEFAULT_BOOST_GRID: List[float] = [0.0, 5.0, 10.0, 20.0, 30.0, 45.0]

_PRETTY = {"ETF": "ETF", "ESG": "ESG", "Region": "Reg", "Theme": "Thm"}


def boost_config_id(boosts: Dict[str, float]) -> str:
    return "boost_" + "_".join(f"{int(round(boosts[k]))}" for k in BOOST_KEYS)


def boost_label(boosts: Dict[str, float]) -> str:
    return "|".join(f"{_PRETTY[k]}={int(round(boosts[k]))}" for k in BOOST_KEYS)


def _make_config(
    boosts: Dict[str, float], is_baseline: bool, kind: Optional[str]
) -> Dict[str, Any]:
    return {
        "config_id": boost_config_id(boosts),
        "label": boost_label(boosts),
        "boost_elevators": dict(boosts),
        # Handed straight to DecisionEngine(**engine_kwargs).
        "engine_kwargs": {"boost_elevators": dict(boosts)},
        "is_baseline": is_baseline,
        "baseline_kind": kind,
    }


def build_boost_configs(
    grid_values: Optional[Sequence[float]] = None,
    *,
    include_live: bool = True,
    include_spec: bool = True,
) -> List[Dict[str, Any]]:
    """Cartesian product over the boost grid for all four boost keys.

    De-duplicated by ``config_id`` and augmented with the live + spec baselines
    so they are guaranteed present even when the grid would not contain them.
    Returns a list sorted by the boost tuple for stable output.
    """
    values = list(grid_values) if grid_values is not None else list(DEFAULT_BOOST_GRID)
    by_id: Dict[str, Dict[str, Any]] = {}
    for combo in itertools.product(values, repeat=len(BOOST_KEYS)):
        boosts = dict(zip(BOOST_KEYS, combo))
        cfg = _make_config(boosts, is_baseline=False, kind=None)
        by_id[cfg["config_id"]] = cfg
    if include_live:
        cfg = _make_config(LIVE_BOOSTS, True, "live")
        by_id[cfg["config_id"]] = cfg
    if include_spec:
        cfg = _make_config(SPEC_BOOSTS, True, "spec")
        by_id[cfg["config_id"]] = cfg
    return sorted(
        by_id.values(),
        key=lambda c: [c["boost_elevators"][k] for k in BOOST_KEYS],
    )


def baseline_configs() -> List[Dict[str, Any]]:
    """Just the two reference baselines (live + spec)."""
    return [
        _make_config(LIVE_BOOSTS, True, "live"),
        _make_config(SPEC_BOOSTS, True, "spec"),
    ]
