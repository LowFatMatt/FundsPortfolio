"""Flexible, deterministic answer-grid generator for DecisionEngine evaluation.

Replaces the rigid two-step generator in ``notes/API-Test-Fonds-Portfolio-
Service.py``: that script only emitted 2-region x 2-theme variants, randomly
capped them, and omitted regions entirely from its first step. This module
enumerates the full engine-relevant answer space — the three single-selects
crossed with *every* region subset (0..len) and *every* theme subset
(0..max_themes) — deterministically, with an optional reproducible stride cap.

Only the dimensions the engine actually consumes are varied (see
``DecisionEngine.recommend``): risk_approach, esg_preference, etf_preference,
preferred_regions, preferred_themes. Other questionnaire fields
(investment_goal, duration, ...) do not affect the output and are omitted.
"""

from __future__ import annotations

import hashlib
import itertools
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

# --- Single-select dimensions (preferences_schema.json) ----------------------
RISK_APPROACHES: List[str] = ["conservative", "moderate", "aggressive"]
ESG_PREFERENCES: List[str] = ["NONE", "PREFER_ESG", "ART_8_9_ONLY"]
ETF_PREFERENCES: List[str] = ["no_preference", "prefer_etf", "etf_only"]

# --- Multi-select vocabularies ----------------------------------------------
# The 5 explicit regions a user can pick (the engine additionally treats
# "global" as a catch-all, but a user never selects "global").
REGIONS: List[str] = [
    "germany",
    "europe",
    "north_america",
    "asia",
    "emerging_markets",
]
MAX_REGIONS_DEFAULT = (
    2  # preferences_schema.json does not cap regions, but the UI does (max 2).
)

# Themes follow the response_schema vocabulary (11 themes incl. "energy", which
# at least one fund carries). "none" is excluded — it means "no theme".
THEMES: List[str] = [
    "sustainability",
    "technology",
    "healthcare",
    "commodities",
    "infrastructure",
    "defense",
    "energy",
    "megatrends",
    "water",
    "ai_robotics",
    "dividends",
]

MAX_THEMES_DEFAULT = 2  # preferences_schema.json: preferred_themes.max == 2


def _stable_id(answer: Dict[str, Any]) -> str:
    """Short deterministic id from the answer contents (for dedupe + join keys)."""
    raw = "|".join(
        [
            str(answer["risk_approach"]),
            str(answer["esg_preference"]),
            str(answer["etf_preference"]),
            ",".join(answer["preferred_regions"]),
            ",".join(answer["preferred_themes"]),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _subsets(options: Sequence[str], max_size: Optional[int]) -> List[List[str]]:
    """All subsets of ``options`` up to ``max_size`` (incl. empty set), each sorted."""
    limit = len(options) if max_size is None else min(max_size, len(options))
    out: List[List[str]] = []
    for size in range(0, limit + 1):
        for combo in itertools.combinations(options, size):
            out.append(sorted(combo))
    return out


def build_answer_grid(
    *,
    max_regions: Optional[int] = MAX_REGIONS_DEFAULT,
    max_themes: int = MAX_THEMES_DEFAULT,
    regions: Optional[Sequence[str]] = None,
    themes: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Enumerate the full engine-relevant answer grid, deterministically.

    Args:
        max_regions: cap on regions per answer (None = all subsets 0..len).
        max_themes: cap on themes per answer (default 2 per schema).
        regions: override region vocabulary.
        themes: override theme vocabulary.

    Returns:
        List of answer dicts. Each has the five user_answers keys plus a
        deterministic ``id``. Order is stable across runs.
    """
    region_opts = list(regions) if regions is not None else list(REGIONS)
    theme_opts = list(themes) if themes is not None else list(THEMES)

    region_subsets = _subsets(region_opts, max_regions)
    theme_subsets = _subsets(theme_opts, max_themes)

    grid: List[Dict[str, Any]] = []
    for risk, esg, etf in itertools.product(
        RISK_APPROACHES, ESG_PREFERENCES, ETF_PREFERENCES
    ):
        for region_sel in region_subsets:
            for theme_sel in theme_subsets:
                answer: Dict[str, Any] = {
                    "risk_approach": risk,
                    "esg_preference": esg,
                    "etf_preference": etf,
                    "preferred_regions": list(region_sel),
                    "preferred_themes": list(theme_sel),
                }
                answer["id"] = _stable_id(answer)
                grid.append(answer)
    return grid


def cap_grid(grid: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
    """Deterministically reduce ``grid`` to ``cap`` entries via stride sampling.

    No RNG: indices ``int(i * n / cap)`` for i in [0, cap) spread the sample
    evenly across the sorted grid so every single-select stratum stays
    represented. Reproducible across runs and machines.
    """
    n = len(grid)
    if cap >= n:
        return list(grid)
    if cap <= 0:
        return []
    step = n / cap
    return [grid[int(i * step)] for i in range(cap)]


def grid_summary(grid: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact structural summary of a grid for logging/reporting."""
    region_counts = Counter(len(a["preferred_regions"]) for a in grid)
    theme_counts = Counter(len(a["preferred_themes"]) for a in grid)
    return {
        "total": len(grid),
        "distinct_ids": len({a["id"] for a in grid}),
        "by_region_count": dict(sorted(region_counts.items())),
        "by_theme_count": dict(sorted(theme_counts.items())),
    }
