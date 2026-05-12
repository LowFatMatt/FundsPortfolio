"""File-backed DataProvider — the only runtime provider."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import DataProvider

logger = logging.getLogger(__name__)


class JsonFileProvider(DataProvider):
    """
    Reads:
      - catalog metadata from `catalog_path` (funds_database.json)
      - per-ISIN time-series from `timeseries_dir`/{ISIN}.json (lazy, cached)
      - benchmarks from `benchmarks_path`

    Read-only: writes happen via offline scripts, never via this class.
    """

    name = "json_file"

    def __init__(
        self,
        catalog_path: str,
        timeseries_dir: str,
        benchmarks_path: str,
    ):
        self.catalog_path = catalog_path
        self.timeseries_dir = timeseries_dir
        self.benchmarks_path = benchmarks_path

        self._funds_cache: Optional[List[Dict[str, Any]]] = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._timeseries_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._benchmarks_cache: Optional[Dict[str, Any]] = None

        self._load_catalog()

    def _load_catalog(self) -> None:
        path = self.catalog_path
        if not os.path.exists(path):
            alt = os.path.join(os.getcwd(), "funds_database.json")
            if os.path.exists(alt):
                logger.debug("catalog not at %s; falling back to %s", path, alt)
                path = alt
                self.catalog_path = alt
        if not os.path.exists(path):
            logger.error("Fund catalog not found at %s", path)
            self._funds_cache = []
            self._metadata = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._funds_cache = data.get("funds_database", [])
            self._metadata = data.get("metadata", {})
            logger.info("Loaded %d funds from %s", len(self._funds_cache), path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load catalog %s: %s", path, exc)
            self._funds_cache = []
            self._metadata = {}

    def list_funds(self) -> List[Dict[str, Any]]:
        return list(self._funds_cache or [])

    def get_fund_meta(self, isin: str) -> Optional[Dict[str, Any]]:
        target = (isin or "").upper()
        for f in self._funds_cache or []:
            if (f.get("isin") or "").upper() == target:
                return f
        return None

    def get_fund_timeseries(self, isin: str) -> Optional[Dict[str, Any]]:
        key = (isin or "").upper()
        if key in self._timeseries_cache:
            return self._timeseries_cache[key]

        path = os.path.join(self.timeseries_dir, f"{key}.json")
        if not os.path.exists(path):
            self._timeseries_cache[key] = None
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._timeseries_cache[key] = data
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load timeseries for %s: %s", key, exc)
            self._timeseries_cache[key] = None
            return None

    def _load_benchmarks(self) -> Dict[str, Any]:
        if self._benchmarks_cache is not None:
            return self._benchmarks_cache
        if not os.path.exists(self.benchmarks_path):
            self._benchmarks_cache = {"benchmarks": {}, "default_by_asset_class": {}}
            return self._benchmarks_cache
        try:
            with open(self.benchmarks_path, "r", encoding="utf-8") as f:
                self._benchmarks_cache = json.load(f) or {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load benchmarks %s: %s", self.benchmarks_path, exc)
            self._benchmarks_cache = {"benchmarks": {}, "default_by_asset_class": {}}
        return self._benchmarks_cache

    def get_benchmark(self, benchmark_id: str) -> Optional[Dict[str, Any]]:
        data = self._load_benchmarks()
        return (data.get("benchmarks") or {}).get(benchmark_id)

    def list_benchmarks(self) -> Dict[str, Any]:
        return dict(self._load_benchmarks())

    def health(self) -> Dict[str, Any]:
        funds = self._funds_cache or []
        timeseries_count = 0
        last_refresh: Optional[str] = None
        if os.path.isdir(self.timeseries_dir):
            for entry in os.scandir(self.timeseries_dir):
                if entry.is_file() and entry.name.endswith(".json"):
                    timeseries_count += 1
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
                    iso = mtime.isoformat()
                    if last_refresh is None or iso > last_refresh:
                        last_refresh = iso
        coverage_pct = round(100.0 * timeseries_count / len(funds), 1) if funds else 0.0
        return {
            "provider_name": self.name,
            "catalog_path": self.catalog_path,
            "timeseries_dir": self.timeseries_dir,
            "fund_count": len(funds),
            "timeseries_count": timeseries_count,
            "coverage_pct": coverage_pct,
            "last_refresh": last_refresh,
            "schema_version": (self._metadata or {}).get("schema_version"),
        }

    def metadata(self) -> Dict[str, Any]:
        return dict(self._metadata or {})
