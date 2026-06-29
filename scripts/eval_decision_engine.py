#!/usr/bin/env python3
"""Evaluate the DecisionEngine on its *current* configuration.

Phase 1 of the tuning plan: build a flexible answer grid, run the in-process
engine over it (no HTTP, no sweep), and write per-answer metrics + an aggregate
summary. Use a cap for a quick smoke run; drop it for the full ~58k grid.

Examples:
    # quick smoke run (1000 answers, single process)
    python scripts/eval_decision_engine.py --answer-grid-cap 1000 --out eval_results

    # full grid, parallel
    python scripts/eval_decision_engine.py --workers 4 --out eval_results

    # narrow the space (e.g. only up to 2 regions, 1 theme)
    python scripts/eval_decision_engine.py --max-regions 2 --max-themes 1
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Allow running from a checkout without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from funds_portfolio.eval.answer_grid import (  # noqa: E402
    build_answer_grid,
    cap_grid,
    grid_summary,
)
from funds_portfolio.eval.reporter import (  # noqa: E402
    aggregate,
    write_csv,
    write_json,
    write_markdown,
)
from funds_portfolio.eval.runner import run_grid  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe",
        default="funds_database.json",
        help="Path to the fund catalog (default: funds_database.json).",
    )
    parser.add_argument(
        "--answer-grid-cap",
        type=int,
        default=None,
        help="Deterministically cap the answer grid to this many entries.",
    )
    parser.add_argument(
        "--max-regions",
        type=int,
        default=None,
        help="Max regions per answer (default: all subsets 0..5).",
    )
    parser.add_argument(
        "--max-themes",
        type=int,
        default=2,
        help="Max themes per answer (default: 2, per schema).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers (1 = single process).",
    )
    parser.add_argument(
        "--out",
        default="eval_results",
        help="Output directory for CSV/JSON/markdown results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log = logging.getLogger("eval")

    grid = build_answer_grid(
        max_regions=args.max_regions, max_themes=args.max_themes
    )
    log.info("full grid: %s", grid_summary(grid))
    if args.answer_grid_cap is not None:
        grid = cap_grid(grid, args.answer_grid_cap)
        log.info("capped grid to %d answers", len(grid))

    records = run_grid(grid, universe_path=args.universe, workers=args.workers)
    summary = aggregate(records)

    os.makedirs(args.out, exist_ok=True)
    write_csv(records, os.path.join(args.out, "per_answer_metrics.csv"))
    write_json(summary, os.path.join(args.out, "summary.json"))
    write_markdown(summary, os.path.join(args.out, "summary.md"))

    log.info("wrote results to %s", args.out)
    print(
        f"Done. {summary['n_answers']} answers evaluated. "
        f"overall mean={summary['overall']['mean']:.3f}, "
        f"pref={summary['pref_score']['mean']:.3f}, "
        f"div={summary['div_score']['mean']:.3f}, "
        f"pct_hijack={summary['behavior']['pct_hijack']:.3f}"
    )


if __name__ == "__main__":
    main()
