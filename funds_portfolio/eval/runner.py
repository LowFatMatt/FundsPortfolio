"""In-process runner: execute ``DecisionEngine.recommend`` over an answer grid.

Phase 1 runs the *current* engine config only (no sweep). Each worker loads the
fund universe once and constructs one ``DecisionEngine`` with the in-tree
defaults, then evaluates its slice of the grid. Embarrassingly parallel;
``workers=1`` runs single-process (used by tests and debugging).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .metrics import compute_metrics

logger = logging.getLogger(__name__)

# Per-worker state, populated by ``_init_worker``.
_WORKER: Dict[str, Any] = {}


def _init_worker(
    universe_path: Optional[str], engine_kwargs: Optional[Dict[str, Any]]
) -> None:
    from funds_portfolio.data.fund_manager import FundManager
    from funds_portfolio.portfolio.decision_engine import DecisionEngine

    _WORKER["funds"] = FundManager(universe_path).get_all_funds()
    _WORKER["engine"] = DecisionEngine(**(engine_kwargs or {}))


def _eval_answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    funds = _WORKER["funds"]
    engine = _WORKER["engine"]
    result = engine.recommend(answer, funds)
    metrics = compute_metrics(answer, result)
    return {
        "answer_id": answer["id"],
        "risk_approach": answer["risk_approach"],
        "esg_preference": answer["esg_preference"],
        "etf_preference": answer["etf_preference"],
        "preferred_regions": ",".join(answer["preferred_regions"]),
        "preferred_themes": ",".join(answer["preferred_themes"]),
        "n_regions": len(answer["preferred_regions"]),
        "n_themes": len(answer["preferred_themes"]),
        **metrics,
    }


def run_grid(
    grid: List[Dict[str, Any]],
    universe_path: Optional[str] = None,
    engine_kwargs: Optional[Dict[str, Any]] = None,
    workers: int = 1,
    progress: bool = True,
) -> List[Dict[str, Any]]:
    """Evaluate every answer in ``grid`` and return one metrics record each."""
    total = len(grid)
    if workers and workers > 1:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(
            workers,
            initializer=_init_worker,
            initargs=(universe_path, engine_kwargs),
        ) as pool:
            records: List[Dict[str, Any]] = []
            for i, rec in enumerate(pool.imap(_eval_answer, grid, chunksize=64), 1):
                records.append(rec)
                if progress and (i % 1000 == 0 or i == total):
                    logger.info("eval %d/%d", i, total)
            return records

    # single process — keeps tests simple and gives usable tracebacks
    _init_worker(universe_path, engine_kwargs)
    records = []
    for i, answer in enumerate(grid, 1):
        records.append(_eval_answer(answer))
        if progress and (i % 1000 == 0 or i == total):
            logger.info("eval %d/%d", i, total)
    return records
