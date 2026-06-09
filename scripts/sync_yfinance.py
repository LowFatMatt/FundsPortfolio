#!/usr/bin/env python3
"""
Sync yfinance price history into data/funds/{ISIN}.json.

A yfinance-backed sibling of sync_factsheetslive.py. For each fund that has a
ticker, this fetches daily prices from Yahoo Finance and writes a timeseries
file in the SAME schema sync_factsheetslive produces, so the GUI charts and
enrich_funds.py read it transparently (no code changes elsewhere).

factsheetslive is authoritative: by default this only writes files for ISINs
that do NOT already have one (gap-fill for funds not yet on factsheetslive).
Pass --overwrite to regenerate existing files from yfinance instead.

Usage:
    PYTHONPATH=. python scripts/sync_yfinance.py --dry-run
    PYTHONPATH=. python scripts/sync_yfinance.py            # gap-fill missing
    PYTHONPATH=. python scripts/sync_yfinance.py --overwrite # force all w/ ticker
    PYTHONPATH=. python scripts/sync_yfinance.py --isin-file new_isins.txt

Conventions (match factsheetslive data/funds files, schema_version 2):
    performance.periods   fractions  (-0.0107 == -1.07%); *_pa keys annualized
    performance.nav_series list of {d: "YYYY-MM-DD", v: float}, rebased to 100
    volatility            by horizon (1y/3y/5y), fraction (0.1599 == 15.99%)
    risk_metrics.sharpe   by horizon, plain ratio (rf = 0)
    risk_metrics.max_drawdown by horizon, NEGATIVE fraction (-0.1602)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from funds_portfolio.data.price_fetcher import PriceFetcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("sync_yfinance")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "funds_database.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "funds"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"

TRADING_DAYS = 252
HORIZON_DAYS = {"1y": 365, "3y": 365 * 3, "5y": 365 * 5}


# --------------------------------------------------------------------------- #
# metric helpers — all operate on a daily-Close Series with a DatetimeIndex
# --------------------------------------------------------------------------- #
def _price_on_or_before(close: pd.Series, target: pd.Timestamp) -> Optional[float]:
    """Last available close at or before `target` (None if series starts later)."""
    window = close.loc[:target]
    if window.empty:
        return None
    return float(window.iloc[-1])


def _trailing_window(close: pd.Series, days: int) -> pd.Series:
    """Slice of the series covering the trailing `days` up to the last point."""
    cutoff = close.index[-1] - pd.Timedelta(days=days)
    return close.loc[close.index >= cutoff]


def _simple_return(close: pd.Series, days: int) -> Optional[float]:
    end = float(close.iloc[-1])
    start = _price_on_or_before(close, close.index[-1] - pd.Timedelta(days=days))
    if start is None or start == 0:
        return None
    return round(end / start - 1.0, 4)


def _cagr(close: pd.Series, days: int) -> Optional[float]:
    """Annualized (per-annum) return over the trailing `days`."""
    end = float(close.iloc[-1])
    start_date = close.index[-1] - pd.Timedelta(days=days)
    start = _price_on_or_before(close, start_date)
    if start is None or start <= 0:
        return None
    span = (close.index[-1] - close.loc[:start_date].index[-1]).days if not close.loc[:start_date].empty else days
    span = max(span, 1)
    return round((end / start) ** (365.25 / span) - 1.0, 4)


def _cagr_since_inception(close: pd.Series) -> Optional[float]:
    end, start = float(close.iloc[-1]), float(close.iloc[0])
    if start <= 0:
        return None
    span = max((close.index[-1] - close.index[0]).days, 1)
    return round((end / start) ** (365.25 / span) - 1.0, 4)


def _ytd(close: pd.Series) -> Optional[float]:
    """Return since last close of the prior calendar year."""
    as_of = close.index[-1]
    prior_year_end = pd.Timestamp(year=as_of.year - 1, month=12, day=31)
    base = _price_on_or_before(close, prior_year_end)
    if base is None or base == 0:
        # No prior-year data; fall back to first point of the current year.
        cur = close.loc[close.index >= pd.Timestamp(year=as_of.year, month=1, day=1)]
        if cur.empty:
            return None
        base = float(cur.iloc[0])
        if base == 0:
            return None
    return round(float(close.iloc[-1]) / base - 1.0, 4)


def _annualized_vol(close: pd.Series, days: int) -> Optional[float]:
    window = _trailing_window(close, days)
    rets = window.pct_change().dropna()
    if len(rets) < 2:
        return None
    return round(float(rets.std() * np.sqrt(TRADING_DAYS)), 4)


def _max_drawdown(close: pd.Series, days: int) -> Optional[float]:
    """Most negative peak-to-trough drawdown over the window, as a fraction."""
    window = _trailing_window(close, days)
    if len(window) < 2:
        return None
    peak = window.cummax()
    dd = (window - peak) / peak
    return round(float(dd.min()), 4)


def _sharpe(close: pd.Series, days: int) -> Optional[float]:
    """Annualized return / annualized volatility over the window (rf = 0)."""
    cagr = _cagr(close, days)
    vol = _annualized_vol(close, days)
    if cagr is None or vol in (None, 0):
        return None
    return round(cagr / vol, 4)


def _nav_series(close: pd.Series) -> List[Dict[str, Any]]:
    """Month-end series rebased to 100 at the first point (factsheetslive style)."""
    monthly = close.resample("ME").last().dropna()
    if monthly.empty:
        return []
    base = float(monthly.iloc[0])
    if base == 0:
        return []
    return [
        {"d": ts.strftime("%Y-%m-%d"), "v": round(float(v) / base * 100.0, 4)}
        for ts, v in monthly.items()
    ]


def build_record(isin: str, ticker: str, fund_meta: Dict[str, Any], prices: pd.DataFrame) -> Dict[str, Any]:
    close = prices["Close"].dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    as_of = close.index[-1].strftime("%Y-%m-%d")

    periods = {
        "3m": _simple_return(close, 91),
        "6m": _simple_return(close, 182),
        "ytd": _ytd(close),
        "1y": _simple_return(close, 365),
        "3y_pa": _cagr(close, HORIZON_DAYS["3y"]),
        "5y_pa": _cagr(close, HORIZON_DAYS["5y"]),
        "si_pa": _cagr_since_inception(close),
    }
    volatility = {h: _annualized_vol(close, d) for h, d in HORIZON_DAYS.items()}
    sharpe = {h: _sharpe(close, d) for h, d in HORIZON_DAYS.items()}
    mdd = {h: _max_drawdown(close, d) for h, d in HORIZON_DAYS.items()}

    return {
        "isin": isin,
        "as_of": as_of,
        "schema_version": 2,
        "source": "yfinance",
        "source_url": f"https://finance.yahoo.com/quote/{ticker}",
        "currency": fund_meta.get("currency"),
        "fund_name": fund_meta.get("name") or fund_meta.get("fund_name"),
        "ticker": ticker,
        "region": fund_meta.get("region"),
        "theme": fund_meta.get("theme"),
        "ter": fund_meta.get("yearly_fee"),
        "sri": fund_meta.get("srri"),
        "performance": {"periods": periods, "nav_series": _nav_series(close)},
        "volatility": volatility,
        "risk_metrics": {"sharpe": sharpe, "max_drawdown": mdd},
        "asset_class_breakdown": None,  # yfinance has none; GUI falls back to catalog
        "top_holdings": None,
    }


def has_any_data(record: Dict[str, Any]) -> bool:
    perf = record.get("performance", {}).get("periods") or {}
    vol = record.get("volatility") or {}
    rm = record.get("risk_metrics") or {}
    return (
        any(v is not None for v in perf.values())
        or any(v is not None for v in vol.values())
        or any(v is not None for d in rm.values() for v in (d or {}).values())
        or bool((record.get("performance") or {}).get("nav_series"))
    )


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_funds(db_path: Path, override_file: Optional[Path], sample: Optional[int]) -> List[Dict[str, Any]]:
    with open(db_path, "r", encoding="utf-8") as f:
        funds = json.load(f).get("funds_database", [])
    by_isin = {(fnd.get("isin") or "").upper(): fnd for fnd in funds if fnd.get("isin")}
    if override_file:
        wanted = [
            ln.strip().upper()
            for ln in override_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        funds = [by_isin[i] for i in wanted if i in by_isin]
        missing = [i for i in wanted if i not in by_isin]
        if missing:
            logger.warning("ISINs in %s not found in DB: %s", override_file, ", ".join(missing))
    if sample:
        funds = funds[:sample]
    return funds


def write_reports(results: List[Dict[str, Any]], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "written": sum(1 for r in results if r["status"] == "written"),
        "skipped_existing": sum(1 for r in results if r["status"] == "skipped_existing"),
        "no_ticker": sum(1 for r in results if r["status"] == "no_ticker"),
        "no_prices": sum(1 for r in results if r["status"] == "no_prices"),
        "empty": sum(1 for r in results if r["status"] == "empty"),
        "total": len(results),
    }
    (report_dir / "yfinance_sync.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    logger.info(
        "Done: %d written, %d skipped(existing), %d no-ticker, %d no-prices, %d empty",
        summary["written"], summary["skipped_existing"], summary["no_ticker"],
        summary["no_prices"], summary["empty"],
    )
    no_ticker = [r["isin"] for r in results if r["status"] == "no_ticker"]
    if no_ticker:
        logger.info("No ticker (add one to funds_database.json to enable): %s", ", ".join(no_ticker))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to funds_database.json")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output dir for {ISIN}.json")
    p.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Where to write the run report")
    p.add_argument("--isin-file", type=Path, default=None, help="Only these ISINs (one per line); default = all funds in DB")
    p.add_argument("--overwrite", action="store_true", help="Regenerate files that already exist (default: skip them)")
    p.add_argument("--use-isin-fallback", action="store_true", help="Try the ISIN as a Yahoo symbol when a fund has no ticker (rarely works for EU funds)")
    p.add_argument("--history-years", type=int, default=5, help="Years of daily history to request")
    p.add_argument("--sample", type=int, default=None, help="Only process the first N funds")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    p.add_argument("--dry-run", action="store_true", help="Compute but do not write files")
    args = p.parse_args(argv)

    funds = load_funds(args.db, args.isin_file, args.sample)
    fetcher = PriceFetcher(history_years=args.history_years)
    logger.info("Processing %d funds (overwrite=%s)", len(funds), args.overwrite)

    results: List[Dict[str, Any]] = []
    for i, fund in enumerate(funds, 1):
        isin = (fund.get("isin") or "").upper()
        out_path = args.output / f"{isin}.json"
        logger.info("[%d/%d] %s", i, len(funds), isin)

        if out_path.exists() and not args.overwrite:
            results.append({"isin": isin, "status": "skipped_existing"})
            continue

        ticker = (fund.get("ticker") or "").strip()
        identifier = ticker or (isin if args.use_isin_fallback else "")
        if not identifier:
            results.append({"isin": isin, "status": "no_ticker"})
            continue

        prices = fetcher.fetch_prices(identifier)
        if prices is None or prices.empty or len(prices) < 2:
            results.append({"isin": isin, "status": "no_prices", "identifier": identifier})
        else:
            record = build_record(isin, identifier, fund, prices)
            if not has_any_data(record):
                results.append({"isin": isin, "status": "empty", "identifier": identifier})
            else:
                if not args.dry_run:
                    atomic_write_json(out_path, record)
                results.append({
                    "isin": isin, "status": "written", "identifier": identifier,
                    "nav_points": len(record["performance"]["nav_series"]),
                    "as_of": record["as_of"],
                })

        if i < len(funds) and args.delay > 0:
            time.sleep(args.delay)

    write_reports(results, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
