"""In-process runner: execute DecisionEngine.recommend over answer grids.

Two entry points:
- ``run_grid``  — one engine config over an answer grid (Phase 1 baseline).
- ``run_sweep`` — many configs over an answer grid (Phase 2 tuning). Results
  stream into per-config accumulators (see ``reporter``), so the full
  configs×answers product never sits in memory.

``workers=1`` runs single-process (tests, debugging, clean tracebacks).
"""

from __future__ import annotations

import itertools
import logging
from typing import Any, Dict, List, Optional, Tuple

from .metrics import compute_metrics
from .reporter import accumulate, finalize, new_accumulator

logger = logging.getLogger(__name__)

_WORKER: Dict[str, Any] = {}
_SWEEP_WORKER: Dict[str, Any] = {"funds": None, "engines": {}}


def _flatten_answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "risk_approach": answer["risk_approach"],
        "esg_preference": answer["esg_preference"],
        "etf_preference": answer["etf_preference"],
        "preferred_regions": ",".join(answer["preferred_regions"]),
        "preferred_themes": ",".join(answer["preferred_themes"]),
        "n_regions": len(answer["preferred_regions"]),
        "n_themes": len(answer["preferred_themes"]),
    }


# --------------------------------------------------------------------------- #
# Phase 1: single config
# --------------------------------------------------------------------------- #
def _init_worker(
    universe_path: Optional[str], engine_kwargs: Optional[Dict[str, Any]]
) -> None:
    from funds_portfolio.data.fund_manager import FundManager
    from funds_portfolio.portfolio.decision_engine import DecisionEngine

    _WORKER["funds"] = FundManager(universe_path).get_all_funds()
    _WORKER["engine"] = DecisionEngine(**(engine_kwargs or {}))


def _eval_answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    result = _WORKER["engine"].recommend(answer, _WORKER["funds"])
    metrics = compute_metrics(answer, result)
    return {"answer_id": answer["id"], **_flatten_answer(answer), **metrics}


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

    _init_worker(universe_path, engine_kwargs)
    records = []
    for i, answer in enumerate(grid, 1):
        records.append(_eval_answer(answer))
        if progress and (i % 1000 == 0 or i == total):
            logger.info("eval %d/%d", i, total)
    return records


# --------------------------------------------------------------------------- #
# Phase 2: config sweep
# --------------------------------------------------------------------------- #
def _init_sweep_worker(universe_path: Optional[str]) -> None:
    from funds_portfolio.data.fund_manager import FundManager

    _SWEEP_WORKER["funds"] = FundManager(universe_path).get_all_funds()
    _SWEEP_WORKER["engines"] = {}


def _engine_for(config: Dict[str, Any]):
    engines = _SWEEP_WORKER["engines"]
    cid = config["config_id"]
    eng = engines.get(cid)
    if eng is None:
        from funds_portfolio.portfolio.decision_engine import DecisionEngine

        eng = DecisionEngine(**config["engine_kwargs"])
        engines[cid] = eng
    return eng


def _eval_pair(task: Tuple[Dict[str, Any], Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    config, answer = task
    eng = _engine_for(config)
    result = eng.recommend(answer, _SWEEP_WORKER["funds"])
    metrics = compute_metrics(answer, result)
    record = {"answer_id": answer["id"], **_flatten_answer(answer), **metrics}
    return config["config_id"], record


def run_sweep(
    grid: List[Dict[str, Any]],
    configs: List[Dict[str, Any]],
    universe_path: Optional[str] = None,
    workers: int = 1,
    progress: bool = True,
) -> List[Dict[str, Any]]:
    """Run every config over every answer; return per-config stats (finalized).

    Streams (config, answer) pairs through ``_eval_pair`` and folds each result
    into a per-config accumulator, so memory is O(#configs), not O(#configs ×
    #answers).
    """
    accs = {c["config_id"]: new_accumulator(c) for c in configs}
    total = len(grid) * len(configs)
    task_iter = itertools.product(configs, grid)

    def _fold(rec: Tuple[str, Dict[str, Any]]) -> None:
        cid, record = rec
        accumulate(accs[cid], record)

    if workers and workers > 1:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(
            workers, initializer=_init_sweep_worker, initargs=(universe_path,)
        ) as pool:
            for i, rec in enumerate(
                pool.imap(_eval_pair, task_iter, chunksize=128), 1
            ):
                _fold(rec)
                if progress and (i % 5000 == 0 or i == total):
                    logger.info("sweep %d/%d (configs=%d)", i, total, len(configs))
    else:
        _init_sweep_worker(universe_path)
        for i, task in enumerate(task_iter, 1):
            _fold(_eval_pair(task))
            if progress and (i % 5000 == 0 or i == total):
                logger.info("sweep %d/%d (configs=%d)", i, total, len(configs))

    return [finalize(accs[c["config_id"]]) for c in configs]
