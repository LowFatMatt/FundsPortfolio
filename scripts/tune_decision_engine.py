#!/usr/bin/env python3
"""Phase 2: sweep BOOST_ELEVATORS configs and rank them.

Builds the answer grid + boost config space, runs every config over every
answer (in-process, parallel), then ranks configs by preference+diversification
and writes a ranked CSV, a markdown recommendation, the full stats JSON, and a
regression snapshot (per-answer selected funds) for the winning config.

Examples:
    # default grid on the 1691-answer sample
    PYTHONPATH=. python scripts/tune_decision_engine.py --answer-grid-cap 1691 --workers 4

    # custom boost grid
    PYTHONPATH=. python scripts/tune_decision_engine.py --boost-grid 0,5,10,20,30,45 --workers 4

    # turn the boost-hijack signal into a penalty
    PYTHONPATH=. python scripts/tune_decision_engine.py --hijack-penalty 0.1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from funds_portfolio.eval.answer_grid import (  # noqa: E402
    build_answer_grid,
    cap_grid,
    grid_summary,
)
from funds_portfolio.eval.config_space import build_boost_configs  # noqa: E402
from funds_portfolio.eval.metrics import compute_metrics  # noqa: E402
from funds_portfolio.eval.ranking import add_diff_vs_live, rank_configs  # noqa: E402
from funds_portfolio.eval.reporter import (  # noqa: E402
    write_configs_csv,
    write_json,
    write_sweep_markdown,
)
from funds_portfolio.eval.runner import run_sweep  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="funds_database.json")
    parser.add_argument("--answer-grid-cap", type=int, default=None)
    parser.add_argument("--max-regions", type=int, default=None)
    parser.add_argument("--max-themes", type=int, default=2)
    parser.add_argument(
        "--boost-grid",
        default="0,5,10,20,30,45",
        help="Comma-separated boost values to sweep (default brackets live Theme=45).",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--pref-weight", type=float, default=0.5)
    parser.add_argument("--div-weight", type=float, default=0.5)
    parser.add_argument(
        "--hijack-penalty",
        type=float,
        default=0.0,
        help="Subtract penalty * pct_hijack from the composite (default 0 = off).",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip writing the regression snapshot for the winning config.",
    )
    parser.add_argument("--out", default="eval_results_sweep")
    return parser.parse_args()


def collect_snapshot(grid, boosts, universe_path):
    """Per-answer selected funds + key metrics for one config (regression golden).

    ``boosts`` is the ``boost_elevators`` dict for the config to snapshot.
    """
    from funds_portfolio.data.fund_manager import FundManager
    from funds_portfolio.portfolio.decision_engine import DecisionEngine

    funds = FundManager(universe_path).get_all_funds()
    engine = DecisionEngine(boost_elevators=boosts)
    rows = []
    for answer in grid:
        result = engine.recommend(answer, funds)
        recs = result.get("recommendations", [])
        metrics = compute_metrics(answer, result)
        rows.append(
            {
                "answer_id": answer["id"],
                "selected": [r.get("isin") for r in recs],
                "allocations": {
                    r.get("isin"): r.get("allocation_percent") for r in recs
                },
                "num_funds": len(recs),
                "overall": metrics["overall"],
                "pref_score": metrics["pref_score"],
                "div_score": metrics["div_score"],
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log = logging.getLogger("tune")

    grid = build_answer_grid(max_regions=args.max_regions, max_themes=args.max_themes)
    log.info("answer grid: %s", grid_summary(grid))
    if args.answer_grid_cap is not None:
        grid = cap_grid(grid, args.answer_grid_cap)
        log.info("capped answer grid to %d", len(grid))

    boost_values = [float(v) for v in args.boost_grid.split(",")]
    configs = build_boost_configs(boost_values)
    log.info("boost configs: %d (grid=%s)", len(configs), boost_values)

    stats = run_sweep(grid, configs, universe_path=args.universe, workers=args.workers)
    add_diff_vs_live(stats)
    ranked = rank_configs(
        stats,
        pref_weight=args.pref_weight,
        div_weight=args.div_weight,
        hijack_penalty=args.hijack_penalty,
    )

    os.makedirs(args.out, exist_ok=True)
    write_configs_csv(ranked, os.path.join(args.out, "configs_ranked.csv"))
    write_json(
        {
            "n_answers": len(grid),
            "n_configs": len(configs),
            "boost_grid": boost_values,
            "pref_weight": args.pref_weight,
            "div_weight": args.div_weight,
            "hijack_penalty": args.hijack_penalty,
            "configs": ranked,
        },
        os.path.join(args.out, "sweep_summary.json"),
    )
    write_sweep_markdown(
        ranked,
        os.path.join(args.out, "sweep_summary.md"),
        n_answers=len(grid),
        pref_weight=args.pref_weight,
        div_weight=args.div_weight,
        hijack_penalty=args.hijack_penalty,
    )

    winner = ranked[0]
    if not args.no_snapshot:
        snap = collect_snapshot(grid, winner["boost_elevators"], args.universe)
        snap_path = os.path.join(
            args.out, f"regression_snapshot_{winner['config_id']}.json"
        )
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "config_id": winner["config_id"],
                    "boost_elevators": winner["boost_elevators"],
                    "n_answers": len(snap),
                    "answers": snap,
                },
                f,
                indent=2,
            )
        log.info("wrote regression snapshot: %s", snap_path)

    log.info("wrote sweep results to %s", args.out)
    wb = winner["boost_elevators"]
    print(
        f"Winner rank 1: ETF={wb['ETF']:.0f} ESG={wb['ESG']:.0f} "
        f"Reg={wb['Region']:.0f} Thm={wb['Theme']:.0f} | "
        f"composite={winner['composite']:.3f} overall={winner['overall_mean']:.3f} "
        f"pref={winner['pref_score_mean']:.3f} div={winner['div_score_mean']:.3f} "
        f"pct_hijack={winner['pct_hijack']:.3f}"
    )


if __name__ == "__main__":
    main()
