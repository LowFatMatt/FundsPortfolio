#!/usr/bin/env python3
"""Generate a large set of test portfolios for later quality/size/trait analysis.

Re-uses two existing mechanisms and fuses them:

* ``scripts/tune_decision_engine.py``  -> the re-runnable CLI pattern (argparse,
  ``--universe``, ``--max-regions``, ``--max-themes``, ``--workers``, ``--out``,
  in-process ``DecisionEngine.recommend``) plus
  ``funds_portfolio.eval.answer_grid`` (``build_answer_grid`` / ``cap_grid`` /
  ``grid_summary``) to define *which* answers exist and how many to draw.

* ``notes/API-Test-Fonds-Portfolio-Service.py`` -> the **two-step strategy**:
  Step 1 runs the 27 hard-filter probes (risk x esg x etf, no regions/themes) to
  discover which ``(risk, esg, etf)`` strata are viable at all; Step 2 takes the
  region/theme expansion of the *viable* strata only, spaces it out with a
  deterministic stride (``cap_grid``), and generates the target number ``N`` of
  portfolios.

Backends
--------
``--backend inprocess`` (default): runs the engine in-process (fast, no server,
reproducible). ``--backend http``: POSTs to the live API (``/api/portfolio``),
like the notes script. Both normalise to the same result shape, so the rest of
the pipeline is identical.

Outputs (under ``--out``, default ``generated_portfolios``)
-----------------------------------------------------------
* ``portfolios/<answer_id>.json``  - one file per of the N step-2 portfolios
  (full engine result: recommendations + portfolio_metrics incl.
  ``preference_satisfaction`` + decision_trace + the user_answers).
* ``portfolios.csv``               - N rows: user_answers + flattened
  ``preference_satisfaction`` columns (see ``CSV_COLUMNS``).
* ``step1_probes/<answer_id>.json`` + ``step1_probes.csv`` - the 27 hard-filter
  probes, written separately (per the agreed semantics, ``N`` counts step-2 only).
* ``manifest.json``                - run config + grid summary + viable strata.

Examples
--------
    # default: 3000 step-2 portfolios, in-process, single worker
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 3000

    # plan only: print grid/counts, write nothing
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 3000 --dry-run

    # parallel in-process
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 3000 --workers 4

    # against the live API (sequential)
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 3000 \
        --backend http --base-url http://fundsportfolio.team79.rocks:5000

    # seed-driven selection: --strategy random makes --seed pick a different,
    # reproducible subset of the answer grid each run (default 'stride' is
    # deterministic and ignores --seed).
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 3000 \
        --strategy random --seed 24 --out gen_seed24

    # narrower space
    PYTHONPATH=. python scripts/generate_test_portfolios.py --n 500 \
        --max-regions 2 --max-themes 1 --out gen_small
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Allow running from a checkout without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from funds_portfolio.eval.answer_grid import (  # noqa: E402
    REGIONS,
    THEMES,
    build_answer_grid,
    cap_grid,
    grid_summary,
)

logger = logging.getLogger("genportfolios")

# --------------------------------------------------------------------------- #
# CSV schema
# --------------------------------------------------------------------------- #
# user_answers (identity + the 5 engine-relevant dims) + flattened
# preference_satisfaction. Per-dimension region/theme columns are left blank when
# that chip was not requested (so "not requested" stays distinct from
# "requested & failed").
REGION_COLUMNS: List[str] = [f"pref_region_{r}" for r in REGIONS]
THEME_COLUMNS: List[str] = [f"pref_theme_{t}" for t in THEMES]
CSV_COLUMNS: List[str] = (
    [
        "answer_id",
        "portfolio_file",
        "status",
        # user_answers
        "risk_approach",
        "esg_preference",
        "etf_preference",
        "preferred_regions",
        "preferred_themes",
        "n_regions",
        "n_themes",
        # preference_satisfaction (summary)
        "pref_fulfilled",
        "pref_total",
        "pref_display",
        # preference_satisfaction (per single-select dimension; always present)
        "pref_risk_approach",
        "pref_esg_preference",
        "pref_etf_preference",
    ]
    + REGION_COLUMNS
    + THEME_COLUMNS
)


# --------------------------------------------------------------------------- #
# Answer-grid helpers
# --------------------------------------------------------------------------- #
def split_two_step(
    grid: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split the grid into the step-1 hard-filter probes and the step-2 pool.

    Step-1 probes are the answers with *no* region and *no* theme preference
    (the 27 risk x esg x etf combinations). Everything else (at least one region
    or theme chip) belongs to the step-2 pool.
    """
    step1 = [
        a for a in grid if not a["preferred_regions"] and not a["preferred_themes"]
    ]
    step2 = [a for a in grid if a["preferred_regions"] or a["preferred_themes"]]
    return step1, step2


def _stratum(answer: Dict[str, Any]) -> Tuple[str, str, str]:
    """The (risk, esg, etf) hard-filter key an answer belongs to."""
    return (
        answer["risk_approach"],
        answer["esg_preference"],
        answer["etf_preference"],
    )


def stratum_breakdown(
    step2_pool: List[Dict[str, Any]],
    viable: set,
    final_step2: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Per-stratum table: viable flag, pool size, and how many were selected."""
    pool_counts = Counter(_stratum(a) for a in step2_pool)
    final_counts = Counter(_stratum(a) for a in final_step2)
    rows = []
    for st in sorted(pool_counts):
        rows.append(
            {
                "risk_approach": st[0],
                "esg_preference": st[1],
                "etf_preference": st[2],
                "viable": st in viable,
                "pool": pool_counts[st],
                "selected": final_counts.get(st, 0),
            }
        )
    return rows


def select_step2(
    candidates: List[Dict[str, Any]],
    n: int,
    *,
    strategy: str = "stride",
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Pick the final ``n`` step-2 answers from the viable-stratum candidates.

    - ``strategy="stride"`` (default): deterministic stride via ``cap_grid`` —
      evenly spread across the grid, identical on every run, and **independent
      of ``seed``**.
    - ``strategy="random"``: seeded shuffle, then take the first ``n`` —
      reproducible per ``seed``; **different seeds select different (but still
      all-viable) subsets**.
    """
    if strategy == "random":
        rng = random.Random(seed)
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        return shuffled[:n]
    return cap_grid(candidates, n)


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
_WORKER: Dict[str, Any] = {}


def _init_inprocess(universe_path: str, language: Optional[str]) -> None:
    """Pool initializer: load the fund universe + a default-config engine once."""
    from funds_portfolio.data.fund_manager import FundManager
    from funds_portfolio.portfolio.decision_engine import DecisionEngine

    _WORKER["funds"] = FundManager(universe_path).get_all_funds()
    _WORKER["engine"] = DecisionEngine()  # production defaults
    _WORKER["language"] = language


def _envelope(
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalise any backend outcome to one shape with a ``status`` flag.

    status is "ok" (>=1 recommendation), "empty" (0 recommendations, no error),
    or "error" (backend raised / 5xx / transport failure). Failed/empty
    portfolios are *recorded*, never raised, so a single bad input (e.g. a
    hard-filter combo with no matching funds -> HTTP 4xx) cannot abort a
    multi-thousand run.
    """
    res = dict(result or {})
    res.setdefault("recommendations", [])
    res.setdefault("risk_profile", None)
    res.setdefault("portfolio_metrics", {})
    res.setdefault("explanations", {})
    res.setdefault("decision_trace", {})
    if status is None:
        status = "error" if error else ("ok" if res["recommendations"] else "empty")
    res["status"] = status
    res["error"] = error
    return res


def _run_inprocess(answer: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = _WORKER["engine"].recommend(
            answer, _WORKER["funds"], language=_WORKER["language"]
        )
        return _envelope(result)
    except Exception as exc:  # pragma: no cover - defensive, keeps the run alive
        logger.exception("in-process recommend failed for answer %s", answer.get("id"))
        return _envelope({}, error=str(exc))


def generate_inprocess(
    answers: List[Dict[str, Any]],
    universe_path: str,
    language: Optional[str] = None,
    workers: int = 1,
    progress: bool = True,
    progress_every: int = 500,
) -> List[Dict[str, Any]]:
    """Run the engine over ``answers`` in-process, optionally parallelised."""
    total = len(answers)
    if not total:
        return []

    if workers and workers > 1:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        results: List[Dict[str, Any]] = []
        with ctx.Pool(
            workers,
            initializer=_init_inprocess,
            initargs=(universe_path, language),
        ) as pool:
            for i, res in enumerate(
                pool.imap(_run_inprocess, answers, chunksize=64), 1
            ):
                results.append(res)
                if progress and (i % progress_every == 0 or i == total):
                    logger.info("inprocess %d/%d", i, total)
        return results

    _init_inprocess(universe_path, language)
    results = []
    for i, a in enumerate(answers, 1):
        results.append(_run_inprocess(a))
        if progress and (i % progress_every == 0 or i == total):
            logger.info("inprocess %d/%d", i, total)
    return results


def _http_post_with_retries(
    user_answers: Dict[str, Any],
    base_url: str,
    language: str,
    timeout: float,
    retries: int,
) -> Any:
    """POST /api/portfolio with simple retries on 5xx / transport errors."""
    import requests  # lazy import: in-process mode must not require it

    url = f"{base_url}/api/portfolio"
    payload = {"user_answers": user_answers, "language": language, "lang": language}
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 2):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code >= 500 and attempt <= retries:
                logger.warning(
                    "HTTP %d on %s, retry %d/%d",
                    resp.status_code,
                    url,
                    attempt,
                    retries,
                )
                time.sleep(1)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "RequestException on %s, retry %d/%d: %s", url, attempt, retries, exc
            )
            if attempt <= retries:
                time.sleep(1)
                continue
            raise
    if last_exc:  # pragma: no cover - defensive
        raise last_exc
    return None


def _run_http(
    answer: Dict[str, Any],
    base_url: str,
    language: str,
    timeout: float,
    retries: int,
) -> Dict[str, Any]:
    """POST one answer; never raises.

    A 4xx 'cannot generate portfolio' (e.g. a hard-filter combo with no matching
    funds) is a *non-viable* outcome and is recorded as an ``empty`` envelope —
    not a fatal error. 5xx / transport failures become ``error`` envelopes. The
    body usually carries ``decision_trace`` explaining why filters eliminated
    everything; we keep it for later analysis.
    """
    try:
        resp = _http_post_with_retries(answer, base_url, language, timeout, retries)
    except Exception as exc:
        logger.error("HTTP transport error for answer %s: %s", answer.get("id"), exc)
        return _envelope({}, error=f"transport: {exc}", status="error")

    try:
        data = resp.json()
    except ValueError:
        data = {}

    body_trace = data.get("decision_trace") or {}
    if resp.status_code >= 500:
        logger.warning(
            "HTTP %d (server) for answer %s after retries -> error envelope",
            resp.status_code,
            answer.get("id"),
        )
        return _envelope(
            {"decision_trace": body_trace},
            error=f"HTTP {resp.status_code}",
            status="error",
        )
    if resp.status_code >= 400:
        logger.info(
            "HTTP %d (cannot generate portfolio) for answer %s -> empty envelope",
            resp.status_code,
            answer.get("id"),
        )
        return _envelope(
            {"decision_trace": body_trace},
            error=f"HTTP {resp.status_code}",
            status="empty",
        )

    # 2xx: normalise the API payload to the engine's result shape.
    pmetrics = data.get("portfolio_metrics") or {}
    return _envelope(
        {
            "portfolio_id": data.get("portfolio_id"),
            "recommendations": data.get("recommendations", []),
            "risk_profile": data.get("risk_profile") or pmetrics.get("risk_profile"),
            "portfolio_metrics": pmetrics,
            "explanations": data.get("explanations") or {},
            "decision_trace": body_trace,
        }
    )


def generate_http(
    answers: List[Dict[str, Any]],
    base_url: str,
    language: str,
    timeout: float,
    retries: int,
    progress: bool = True,
    progress_every: int = 100,
) -> List[Dict[str, Any]]:
    """Run answers through the live HTTP API (sequential, with retries)."""
    total = len(answers)
    results: List[Dict[str, Any]] = []
    for i, a in enumerate(answers, 1):
        results.append(_run_http(a, base_url, language, timeout, retries))
        if progress and (i % progress_every == 0 or i == total):
            logger.info("http %d/%d", i, total)
    return results


def run_via_backend(
    answers: List[Dict[str, Any]], args: argparse.Namespace, progress: bool = True
) -> List[Dict[str, Any]]:
    if args.backend == "http":
        return generate_http(
            answers,
            base_url=args.base_url,
            language=args.language,
            timeout=args.http_timeout,
            retries=args.http_retries,
            progress=progress,
        )
    return generate_inprocess(
        answers,
        universe_path=args.universe,
        language=args.language,
        workers=args.workers,
        progress=progress,
    )


# --------------------------------------------------------------------------- #
# Result extraction
# --------------------------------------------------------------------------- #
def is_viable(result: Dict[str, Any]) -> bool:
    """A profile is viable if the engine returned at least one fund."""
    return len(result.get("recommendations") or []) > 0


def extract_preference_satisfaction(
    result: Dict[str, Any], answer: Dict[str, Any]
) -> Dict[str, Any]:
    """Pull the preference_satisfaction dict out of a result; recompute if absent.

    Both backends embed it under ``portfolio_metrics`` (and ``decision_trace``).
    The recompute fallback keeps the pipeline robust if a backend ever omits it.
    """
    pmetrics = result.get("portfolio_metrics") or {}
    trace = result.get("decision_trace") or {}
    ps = pmetrics.get("preference_satisfaction") or trace.get("preference_satisfaction")
    if ps:
        return ps

    from funds_portfolio.portfolio.preference_match import preference_satisfaction

    return preference_satisfaction(
        answer,
        result.get("recommendations") or [],
        relaxations=trace.get("relaxations") or [],
        used_fallback_risk=bool(trace.get("used_fallback_risk")),
    )


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_portfolio_json(
    out_root: str,
    subdir: str,
    answer: Dict[str, Any],
    result: Dict[str, Any],
    step: int,
    backend: str,
) -> str:
    """Persist one portfolio artifact; return its path relative to ``out_root``."""
    rel = f"{subdir}/{answer['id']}.json"
    path = os.path.join(out_root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    artifact = {
        "answer_id": answer["id"],
        "step": step,
        "backend": backend,
        "user_answers": {
            "risk_approach": answer.get("risk_approach"),
            "esg_preference": answer.get("esg_preference"),
            "etf_preference": answer.get("etf_preference"),
            "preferred_regions": list(answer.get("preferred_regions") or []),
            "preferred_themes": list(answer.get("preferred_themes") or []),
        },
        **result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    return rel


def build_csv_row(
    answer: Dict[str, Any], result: Dict[str, Any], portfolio_file: str
) -> Dict[str, Any]:
    """Flatten one (answer, result) into the CSV schema (``CSV_COLUMNS``).

    For non-ok results (``status != "ok"``) the preference_satisfaction columns
    are left blank: an empty/failed portfolio has no meaningful satisfaction,
    and synthesising one from zero recommendations would be misleading.
    """
    status = result.get("status", "ok")

    # Defaults: identity + user_answers always populated; preference_satisfaction
    # columns blank unless status == "ok".
    row: Dict[str, Any] = {
        "answer_id": answer["id"],
        "portfolio_file": portfolio_file,
        "status": status,
        "risk_approach": answer["risk_approach"],
        "esg_preference": answer["esg_preference"],
        "etf_preference": answer["etf_preference"],
        "preferred_regions": "|".join(answer["preferred_regions"]),
        "preferred_themes": "|".join(answer["preferred_themes"]),
        "n_regions": len(answer["preferred_regions"]),
        "n_themes": len(answer["preferred_themes"]),
        "pref_fulfilled": None,
        "pref_total": None,
        "pref_display": None,
        "pref_risk_approach": None,
        "pref_esg_preference": None,
        "pref_etf_preference": None,
    }
    for r in REGIONS:
        row[f"pref_region_{r}"] = None
    for t in THEMES:
        row[f"pref_theme_{t}"] = None

    if status == "ok":
        ps = extract_preference_satisfaction(result, answer)
        # Map (dimension, value_lower) -> fulfilled for the per-dimension columns.
        fulfilled_by_dim_value: Dict[Tuple[str, str], Any] = {}
        for item in ps.get("per_item") or []:
            dim = item.get("dimension")
            val = str(item.get("value") or "").lower()
            fulfilled_by_dim_value[(dim, val)] = bool(item.get("fulfilled"))
        row["pref_fulfilled"] = ps.get("fulfilled")
        row["pref_total"] = ps.get("total")
        row["pref_display"] = ps.get("display")
        row["pref_risk_approach"] = fulfilled_by_dim_value.get(
            ("risk_approach", str(answer["risk_approach"]).lower())
        )
        row["pref_esg_preference"] = fulfilled_by_dim_value.get(
            ("esg_preference", str(answer["esg_preference"]).lower())
        )
        row["pref_etf_preference"] = fulfilled_by_dim_value.get(
            ("etf_preference", str(answer["etf_preference"]).lower())
        )
        for r in REGIONS:
            row[f"pref_region_{r}"] = fulfilled_by_dim_value.get(
                ("preferred_regions", r)
            )
        for t in THEMES:
            row[f"pref_theme_{t}"] = fulfilled_by_dim_value.get(("preferred_themes", t))
    return row


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(obj: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Dry-run reporter
# --------------------------------------------------------------------------- #
def print_dry_run_summary(
    args: argparse.Namespace,
    grid: List[Dict[str, Any]],
    step1: List[Dict[str, Any]],
    step2_pool: List[Dict[str, Any]],
    viable: set,
    step2_candidates: List[Dict[str, Any]],
    final_step2: List[Dict[str, Any]],
) -> None:
    print("=" * 72)
    print("DRY RUN — nothing will be written")
    print("=" * 72)
    print(f"backend        : {args.backend}")
    print(f"universe       : {args.universe}")
    print(f"max_regions    : {args.max_regions}")
    print(f"max_themes     : {args.max_themes}")
    print(f"n requested    : {args.n}")
    print(
        f"strategy       : {args.strategy}"
        + (
            "  (seed has no effect; deterministic stride)"
            if args.strategy == "stride"
            else f"  (seed={args.seed} controls the subset)"
        )
    )
    print(f"seed           : {args.seed}")
    print("-" * 72)
    print(f"full grid      : {grid_summary(grid)}")
    print(f"step-1 probes  : {len(step1)}  (risk x esg x etf, no regions/themes)")
    print(f"step-2 pool    : {len(step2_pool)}  (>=1 region or theme chip)")
    print(
        f"viable strata  : {len(viable)}/{len(step1)}  (probes that returned >=1 fund)"
    )
    print(
        f"step-2 viable  : {len(step2_candidates)} candidates "
        f"-> {args.strategy} to {args.n} = {len(final_step2)} to generate"
    )
    if len(final_step2) < args.n:
        print(
            f"  NOTE: fewer than --n={args.n} viable candidates; "
            f"only {len(final_step2)} would be generated."
        )
    print("-" * 72)
    print("per-stratum breakdown (step-2):")
    print(
        f"  {'risk':<13}{'esg':<14}{'etf':<14}{'viable':<8}{'pool':>7}{'selected':>10}"
    )
    for row in stratum_breakdown(step2_pool, viable, final_step2):
        print(
            f"  {row['risk_approach']:<13}{row['esg_preference']:<14}"
            f"{row['etf_preference']:<14}{str(row['viable']):<8}"
            f"{row['pool']:>7}{row['selected']:>10}"
        )
    print("=" * 72)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--universe",
        default="funds_database.json",
        help="Path to the fund catalog (default: funds_database.json).",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=3000,
        help="Number of step-2 portfolios to generate (default: 3000).",
    )
    parser.add_argument("--max-regions", type=int, default=2)
    parser.add_argument("--max-themes", type=int, default=2)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers for the in-process backend (default: 1).",
    )
    parser.add_argument(
        "--out",
        default="generated_portfolios",
        help="Output directory (default: generated_portfolios).",
    )
    parser.add_argument(
        "--backend",
        choices=["inprocess", "http"],
        default="inprocess",
        help="How to run the engine (default: inprocess).",
    )
    parser.add_argument(
        "--base-url",
        default="http://fundsportfolio.team79.rocks:5000",
        help="Base URL for --backend http (default: live service).",
    )
    parser.add_argument(
        "--language", default="de", help="Language passed to the engine/API."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed. Only affects --strategy random (different seed -> "
        "different subset) and HTTP reproducibility; ignored by the default "
        "--strategy stride (default: 42).",
    )
    parser.add_argument(
        "--strategy",
        choices=["stride", "random"],
        default="stride",
        help="How to pick the N step-2 answers from the viable candidates. "
        "'stride' (default) = deterministic, evenly spread, ignores --seed. "
        "'random' = seeded shuffle; --seed controls which subset is picked.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only: print grid/counts and viable-strata table, write nothing.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=10.0,
        help="Per-request timeout (s) for --backend http (default: 10).",
    )
    parser.add_argument(
        "--http-retries",
        type=int,
        default=2,
        help="Retries on 5xx/transport errors for --backend http (default: 2).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    # 1) Build the grid and split it into the two steps.
    grid = build_answer_grid(max_regions=args.max_regions, max_themes=args.max_themes)
    logger.info("full grid: %s", grid_summary(grid))
    step1, step2_pool = split_two_step(grid)
    logger.info("split: step-1 probes=%d, step-2 pool=%d", len(step1), len(step2_pool))

    # 2) Step 1: run the hard-filter probes to learn which strata are viable.
    #    Dry-run always uses the in-process engine for planning (fast, no server).
    if args.dry_run and args.backend != "inprocess":
        logger.info("dry-run: forcing in-process backend for step-1 probes")
    probe_backend = "inprocess" if args.dry_run else args.backend
    if args.dry_run:
        probe_results = generate_inprocess(
            step1,
            universe_path=args.universe,
            language=args.language,
            workers=args.workers,
            progress=False,
        )
    else:
        probe_results = run_via_backend(step1, args)

    viable: set = set()
    for a, r in zip(step1, probe_results):
        if is_viable(r):
            viable.add(_stratum(a))
    logger.info("viable (risk,esg,etf) strata: %d/%d", len(viable), len(step1))

    # 3) Step 2: keep only viable-stratum answers, then pick N of them.
    step2_candidates = [a for a in step2_pool if _stratum(a) in viable]
    logger.info("step-2 candidates (viable strata): %d", len(step2_candidates))
    final_step2 = select_step2(
        step2_candidates, args.n, strategy=args.strategy, seed=args.seed
    )
    logger.info(
        "step-2 final (strategy=%s, n=%d): %d", args.strategy, args.n, len(final_step2)
    )
    if len(final_step2) < args.n:
        logger.warning(
            "only %d viable step-2 candidates (< --n=%d); generating all of them.",
            len(final_step2),
            args.n,
        )

    # 4) Dry-run stops here: print the plan, write nothing.
    if args.dry_run:
        print_dry_run_summary(
            args, grid, step1, step2_pool, viable, step2_candidates, final_step2
        )
        return

    # 5) Generate for real.
    os.makedirs(args.out, exist_ok=True)
    portfolios_dir_rel = "portfolios"
    probes_dir_rel = "step1_probes"

    # 5a) Step-1 probe portfolios + CSV rows (reusing the probe results).
    probe_rows: List[Dict[str, Any]] = []
    for a, r in zip(step1, probe_results):
        rel = write_portfolio_json(
            args.out, probes_dir_rel, a, r, step=1, backend=probe_backend
        )
        probe_rows.append(build_csv_row(a, r, rel))
    logger.info("wrote %d step-1 probe portfolios", len(probe_rows))

    # 5b) Step-2 portfolios + CSV rows.
    step2_results = run_via_backend(final_step2, args)
    step2_rows: List[Dict[str, Any]] = []
    for a, r in zip(final_step2, step2_results):
        rel = write_portfolio_json(
            args.out, portfolios_dir_rel, a, r, step=2, backend=args.backend
        )
        step2_rows.append(build_csv_row(a, r, rel))
    logger.info("wrote %d step-2 portfolios", len(step2_rows))

    # Status tallies (ok / empty / error) for visibility on partial runs.
    probe_status = Counter(r.get("status", "ok") for r in probe_results)
    step2_status = Counter(r.get("status", "ok") for r in step2_results)
    logger.info(
        "step-1 status: ok=%d empty=%d error=%d",
        probe_status.get("ok", 0),
        probe_status.get("empty", 0),
        probe_status.get("error", 0),
    )
    logger.info(
        "step-2 status: ok=%d empty=%d error=%d",
        step2_status.get("ok", 0),
        step2_status.get("empty", 0),
        step2_status.get("error", 0),
    )
    n_step2_not_ok = step2_status.get("empty", 0) + step2_status.get("error", 0)
    if n_step2_not_ok:
        logger.warning(
            "%d step-2 portfolio(s) could not be generated "
            "(see the status column / per-portfolio JSON); run continues.",
            n_step2_not_ok,
        )

    # 6) CSVs + manifest.
    write_csv(os.path.join(args.out, "portfolios.csv"), step2_rows)
    write_csv(os.path.join(args.out, "step1_probes.csv"), probe_rows)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_requested": args.n,
        "n_generated_step2": len(step2_rows),
        "n_step1_probes": len(probe_rows),
        "status_counts_step1": dict(probe_status),
        "status_counts_step2": dict(step2_status),
        "backend": args.backend,
        "base_url": args.base_url if args.backend == "http" else None,
        "language": args.language,
        "universe": args.universe,
        "max_regions": args.max_regions,
        "max_themes": args.max_themes,
        "seed": args.seed,
        "strategy": args.strategy,
        "engine": "DecisionEngine (production defaults)",
        "grid_summary_full": grid_summary(grid),
        "grid_summary_step2": grid_summary(step2_candidates),
        "viable_strata": [
            {"risk_approach": s[0], "esg_preference": s[1], "etf_preference": s[2]}
            for s in sorted(viable)
        ],
        "stratum_breakdown": stratum_breakdown(step2_pool, viable, final_step2),
        "csv_columns": CSV_COLUMNS,
    }
    write_json(manifest, os.path.join(args.out, "manifest.json"))

    logger.info("wrote outputs to %s", args.out)
    n_step2_ok = step2_status.get("ok", 0)
    print(
        f"Done. {n_step2_ok} step-2 portfolios generated"
        + (f" (+ {n_step2_not_ok} empty/failed)" if n_step2_not_ok else "")
        + f" + {len(probe_rows)} step-1 probes written to {args.out}/"
    )
    print(
        f"  - {portfolios_dir_rel}/  ({len(step2_rows)} *.json) + portfolios.csv\n"
        f"  - {probes_dir_rel}/  ({len(probe_rows)} *.json) + step1_probes.csv\n"
        f"  - manifest.json"
    )


if __name__ == "__main__":
    main()
