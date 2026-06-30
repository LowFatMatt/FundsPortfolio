"""Decision-engine evaluation harness.

Phase 1: measure a single config (``run_grid`` + ``aggregate``).
Phase 2: sweep BOOST_ELEVATORS configs (``run_sweep`` + ranking/reporters).
"""

from .answer_grid import build_answer_grid, cap_grid, grid_summary
from .config_space import (
    DEFAULT_BOOST_GRID,
    LIVE_BOOSTS,
    SPEC_BOOSTS,
    baseline_configs,
    build_boost_configs,
)
from .metrics import compute_metrics
from .ranking import add_diff_vs_live, composite_score, pareto_front, rank_configs
from .reporter import (
    accumulate,
    aggregate,
    finalize,
    new_accumulator,
    write_configs_csv,
    write_csv,
    write_json,
    write_markdown,
    write_sweep_markdown,
)
from .runner import run_grid, run_sweep

__all__ = [
    "build_answer_grid",
    "cap_grid",
    "grid_summary",
    "compute_metrics",
    "run_grid",
    "run_sweep",
    "aggregate",
    "write_csv",
    "write_json",
    "write_markdown",
    "new_accumulator",
    "accumulate",
    "finalize",
    "build_boost_configs",
    "baseline_configs",
    "LIVE_BOOSTS",
    "SPEC_BOOSTS",
    "DEFAULT_BOOST_GRID",
    "rank_configs",
    "pareto_front",
    "composite_score",
    "add_diff_vs_live",
    "write_configs_csv",
    "write_sweep_markdown",
]
