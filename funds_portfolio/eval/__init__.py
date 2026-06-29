"""Decision-engine evaluation harness.

Phase 1: measure the *current* (in-tree) DecisionEngine configuration over a
flexible, deterministic answer grid. No config sweep yet — the goal is to
validate the measurement (preference-satisfaction + diversification + a
boost-hijack diagnostic) before tuning anything.
"""

from .answer_grid import build_answer_grid, cap_grid, grid_summary
from .metrics import compute_metrics
from .reporter import aggregate, write_csv, write_json, write_markdown
from .runner import run_grid

__all__ = [
    "build_answer_grid",
    "cap_grid",
    "grid_summary",
    "compute_metrics",
    "run_grid",
    "aggregate",
    "write_csv",
    "write_json",
    "write_markdown",
]
