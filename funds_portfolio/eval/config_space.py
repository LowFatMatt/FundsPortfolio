"""Configuration space for the DecisionEngine sweep.

Primary lever: ``BOOST_ELEVATORS`` (ETF/ESG/Region/Theme). The live in-tree
values are **derived from the engine itself** (imported), so the "live"
baseline can never drift from the code it claims to mirror — the drift that
silently invalidated earlier sweeps (LIVE said 20/30/45 while the engine ran
45/70/70) is now structurally impossible. The spec v3.2 values coincide with
the engine defaults (all boosts are nominal tie-breakers now — ETF/ESG +6,
Region/Theme 0; preferences are honored structurally via pass-1 coverage,
hard filters and dialog gating, see FUND_SELECTION_LOGIC_SPEC_V3.md Step 6),
so the "spec" baseline collapses into "live" and is only emitted when it
differs.

The default grid ``[0, 2, 6, 10, 20, 30, 45]`` contains every live value so
the status quo is explored, not just diffed against from outside the grid.

Secondary knobs (scoring weights, caps, risk bands, tier bounds, satellite
cap, regional tilt) are intentionally NOT materialised here yet — Phase 2
focuses on boosts; they are queued for a later stage if the boost sweep
plateaus.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Sequence

from ..portfolio.decision_engine import BOOST_ELEVATORS as _ENGINE_BOOSTS

# Canonical boost keys; must match decision_engine.BOOST_ELEVATORS.
BOOST_KEYS = ("ETF", "ESG", "Region", "Theme")

# Live in-tree values — DERIVED from the engine (drift-proof by construction).
LIVE_BOOSTS: Dict[str, float] = dict(_ENGINE_BOOSTS)

# Spec v3.2 values (FUND_SELECTION_LOGIC_SPEC_V3.md, Step 6 table). Kept as a
# literal so tests can assert the engine implements the spec; equals the
# engine default, so no separate "spec" baseline config is emitted.
SPEC_BOOSTS: Dict[str, float] = {
    "ETF": 6.0,
    "ESG": 6.0,
    "Region": 0.0,
    "Theme": 0.0,
}

# Contains every live value (incl. the +6 ETF/ESG tie-breakers).
DEFAULT_BOOST_GRID: List[float] = [0.0, 2.0, 6.0, 10.0, 20.0, 30.0, 45.0]

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
    # Post-v3.1 the spec defaults equal the engine defaults; emit a separate
    # "spec" baseline only when the two actually diverge (a meaningful
    # contrast), never as a duplicate of "live".
    if include_spec and SPEC_BOOSTS != LIVE_BOOSTS:
        cfg = _make_config(SPEC_BOOSTS, True, "spec")
        by_id[cfg["config_id"]] = cfg
    return sorted(
        by_id.values(),
        key=lambda c: [c["boost_elevators"][k] for k in BOOST_KEYS],
    )


def baseline_configs() -> List[Dict[str, Any]]:
    """The reference baselines: always "live"; plus "spec" only if it differs."""
    out = [_make_config(LIVE_BOOSTS, True, "live")]
    if SPEC_BOOSTS != LIVE_BOOSTS:
        out.append(_make_config(SPEC_BOOSTS, True, "spec"))
    return out
