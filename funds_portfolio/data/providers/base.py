"""Abstract DataProvider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DataProvider(ABC):
    """
    Read-only fund-data source.

    All methods are synchronous and assume the underlying data is already
    available locally. Live scrapers must populate the local cache offline
    before the runtime consults the provider.
    """

    name: str = "abstract"

    @abstractmethod
    def list_funds(self) -> List[Dict[str, Any]]:
        """Return all fund metadata records (one dict per fund)."""

    @abstractmethod
    def get_fund_meta(self, isin: str) -> Optional[Dict[str, Any]]:
        """Return metadata for a single ISIN, or None if not found."""

    @abstractmethod
    def get_fund_timeseries(self, isin: str) -> Optional[Dict[str, Any]]:
        """
        Return the time-varying block for an ISIN:
        {as_of, currency, performance:{periods, nav_series}, volatility, risk_metrics, top_holdings?}
        or None if no timeseries file exists for the ISIN.
        """

    @abstractmethod
    def get_benchmark(self, benchmark_id: str) -> Optional[Dict[str, Any]]:
        """Return a benchmark series by id (e.g. 'msci_world')."""

    @abstractmethod
    def list_benchmarks(self) -> Dict[str, Any]:
        """
        Return the full benchmarks config:
        {benchmarks: {id: {...}}, default_by_asset_class: {...}}
        """

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """
        Return provider status:
        {provider_name, last_refresh, fund_count, timeseries_count, coverage_pct}
        """
