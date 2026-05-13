"""
Data-provider abstraction.

Runtime is cache-first: the Flask app only reads from a provider that
serves pre-populated data from disk. Scrapers (offline) write files that
conform to the same JSON shape consumed by JsonFileProvider.

Select the active provider with the FUNDS_DATA_PROVIDER env var; per-provider
config is loaded from data_sources.yaml at the repo root (PyYAML if available,
otherwise a small parser for the flat structure we use).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .base import DataProvider
from .json_file import JsonFileProvider

logger = logging.getLogger(__name__)

_provider_instance: Optional[DataProvider] = None


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _load_data_sources_config() -> dict:
    """
    Read data_sources.yaml from the repo root.

    Falls back to a hardcoded default if the file or PyYAML is unavailable.
    """
    config_path = os.path.join(_repo_root(), "data_sources.yaml")
    if not os.path.exists(config_path):
        return _default_config()

    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning("PyYAML not installed; using default data-sources config")
        return _default_config()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or _default_config()
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load %s: %s", config_path, exc)
        return _default_config()


def _default_config() -> dict:
    root = _repo_root()
    return {
        "default": "json_file",
        "providers": {
            "json_file": {
                "catalog_path": os.path.join(root, "funds_database.json"),
                "timeseries_dir": os.path.join(root, "data", "funds"),
                "benchmarks_path": os.path.join(root, "data", "benchmarks.json"),
            }
        },
    }


def get_provider(name: Optional[str] = None) -> DataProvider:
    """
    Return the configured DataProvider singleton.

    Resolution order: explicit `name` arg → FUNDS_DATA_PROVIDER env var →
    the `default` key in data_sources.yaml.
    """
    global _provider_instance
    if _provider_instance is not None and name is None:
        return _provider_instance

    config = _load_data_sources_config()
    chosen = name or os.getenv("FUNDS_DATA_PROVIDER") or config.get("default", "json_file")
    provider_cfg = (config.get("providers") or {}).get(chosen) or {}

    root = _repo_root()

    def _resolve(value: Optional[str], default_rel: str) -> str:
        value = value or default_rel
        return value if os.path.isabs(value) else os.path.join(root, value)

    catalog_path = _resolve(provider_cfg.get("catalog_path"), "funds_database.json")
    timeseries_dir = _resolve(provider_cfg.get("timeseries_dir"), os.path.join("data", "funds"))
    benchmarks_path = _resolve(provider_cfg.get("benchmarks_path"), os.path.join("data", "benchmarks.json"))

    # Customer-profile override: if CUSTOMER is set and that profile's catalog
    # exists, prefer it over the configured / default catalog path. Falls back
    # silently to the original path otherwise, so tests and legacy deploys are
    # unaffected.
    customer = os.getenv("CUSTOMER")
    if customer:
        customer_catalog = os.path.join(root, "data", "customers", customer, "funds_database.json")
        if os.path.exists(customer_catalog):
            logger.info("CUSTOMER=%s → using catalog %s", customer, customer_catalog)
            catalog_path = customer_catalog
        else:
            logger.warning(
                "CUSTOMER=%s set but %s does not exist; falling back to %s",
                customer, customer_catalog, catalog_path,
            )

    if chosen != "json_file":
        logger.warning(
            "Provider '%s' is not supported at runtime; falling back to json_file. "
            "Scrapers must run offline and write JSON files for json_file to read.",
            chosen,
        )

    instance = JsonFileProvider(
        catalog_path=catalog_path,
        timeseries_dir=timeseries_dir,
        benchmarks_path=benchmarks_path,
    )
    _provider_instance = instance
    return instance


def reset_provider() -> None:
    """Test hook: drop the cached provider so the next get_provider() rebuilds."""
    global _provider_instance
    _provider_instance = None


__all__ = ["DataProvider", "JsonFileProvider", "get_provider", "reset_provider"]
