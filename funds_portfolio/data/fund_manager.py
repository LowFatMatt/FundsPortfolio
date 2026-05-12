"""
FundManager — read-only facade over the configured DataProvider.

Preserves the public read API used by the decision engine and tests:
  get_all_funds, get_fund_by_isin, get_funds_by_risk_level,
  get_funds_by_asset_class, get_funds_by_category, get_metadata,
  is_loaded, load_funds.

New pass-throughs for Phase 2 features:
  get_fund_timeseries, get_benchmark, list_benchmarks, health.

Runtime writes are no longer supported here — see scripts/ for ingestion.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from .providers import DataProvider, JsonFileProvider, get_provider

logger = logging.getLogger(__name__)


class FundManager:
    """Read-only fund data accessor."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: Optional explicit path to funds_database.json. When
                provided, a dedicated JsonFileProvider is built around that
                path (used by tests for isolation). When omitted, the global
                provider configured via data_sources.yaml / FUNDS_DATA_PROVIDER
                is used.
        """
        self._provider: DataProvider
        if db_path is not None:
            if not os.path.exists(db_path):
                alt = os.path.join(os.getcwd(), "funds_database.json")
                if os.path.exists(alt):
                    db_path = alt
            timeseries_dir = os.path.join(os.path.dirname(db_path), "data", "funds")
            if not os.path.isdir(timeseries_dir):
                timeseries_dir = os.path.join(os.getcwd(), "data", "funds")
            benchmarks_path = os.path.join(os.path.dirname(db_path), "data", "benchmarks.json")
            if not os.path.exists(benchmarks_path):
                benchmarks_path = os.path.join(os.getcwd(), "data", "benchmarks.json")
            self._provider = JsonFileProvider(
                catalog_path=db_path,
                timeseries_dir=timeseries_dir,
                benchmarks_path=benchmarks_path,
            )
        else:
            self._provider = get_provider()

    # --- Catalog reads ---

    def load_funds(self) -> bool:
        """Backward-compat no-op: providers self-load."""
        return self.is_loaded()

    def get_all_funds(self) -> List[Dict]:
        return self._provider.list_funds()

    def get_fund_by_isin(self, isin: str) -> Optional[Dict]:
        return self._provider.get_fund_meta(isin)

    def get_funds_by_risk_level(self, risk_level: int) -> List[Dict]:
        return [f for f in self.get_all_funds() if f.get("risk_level") == risk_level]

    def get_funds_by_asset_class(self, asset_class: str) -> List[Dict]:
        target = (asset_class or "").lower()
        return [f for f in self.get_all_funds() if (f.get("asset_class") or "").lower() == target]

    def get_funds_by_category(self, category: str) -> List[Dict]:
        return [f for f in self.get_all_funds() if category in (f.get("categories") or [])]

    def get_metadata(self) -> Dict:
        if hasattr(self._provider, "metadata"):
            return self._provider.metadata()  # type: ignore[attr-defined]
        return {}

    def is_loaded(self) -> bool:
        return bool(self._provider.list_funds())

    # --- Phase 2 pass-throughs ---

    def get_fund_timeseries(self, isin: str) -> Optional[Dict]:
        return self._provider.get_fund_timeseries(isin)

    def get_benchmark(self, benchmark_id: str) -> Optional[Dict]:
        return self._provider.get_benchmark(benchmark_id)

    def list_benchmarks(self) -> Dict:
        return self._provider.list_benchmarks()

    def health(self) -> Dict:
        return self._provider.health()


_fund_manager_instance: Optional[FundManager] = None


def get_fund_manager(db_path: Optional[str] = None) -> FundManager:
    """
    Get or create the global FundManager singleton.

    Args:
        db_path: Optional path; only honoured on the first call. Subsequent
            calls return the existing singleton regardless of this argument.
    """
    global _fund_manager_instance
    if _fund_manager_instance is None:
        _fund_manager_instance = FundManager(db_path)
    return _fund_manager_instance


def reset_fund_manager() -> None:
    """Test hook to drop the singleton."""
    global _fund_manager_instance
    _fund_manager_instance = None
