"""
Stress-period config loader.

Stress periods are app-level overlay configuration, not fund data — so they
sit outside the DataProvider abstraction. Edit data/stress_periods.json to
add/remove overlays; the frontend gets toggle chips for each entry.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def _default_path() -> str:
    return os.path.join(_repo_root(), "data", "stress_periods.json")


_cache: Optional[Dict[str, Any]] = None


def load_stress_periods(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Return {schema_version, stress_periods: [...]}; empty list if missing.

    Cached after first load — call reload_stress_periods() to force a re-read.
    """
    global _cache
    if _cache is not None and path is None:
        return _cache

    target = path or _default_path()
    if not os.path.exists(target):
        logger.info("No stress_periods.json found at %s — overlays disabled", target)
        result: Dict[str, Any] = {"schema_version": 1, "stress_periods": []}
        if path is None:
            _cache = result
        return result

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load stress_periods from %s: %s", target, exc)
        data = {"schema_version": 1, "stress_periods": []}

    if path is None:
        _cache = data
    return data


def list_stress_periods(path: Optional[str] = None) -> List[Dict[str, Any]]:
    return load_stress_periods(path).get("stress_periods", [])


def reload_stress_periods() -> None:
    global _cache
    _cache = None
