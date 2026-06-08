from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_percent(value: str) -> Optional[float]:
    if value is None:
        return None
    cleaned = value.strip().replace("%", "").replace(",", ".")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


ASSET_LABEL_ALIASES = {
    "barmittel": "cash",
    "geldmarkt": "cash",
    "liquid": "cash",
    "liquid funds": "cash",
}


def load_i18n_asset_map() -> Dict[str, str]:
    """Load i18n files and return mapping from localized label (lowercase) to canonical asset key.

    Example: "Aktien" -> "equity"
    """
    mapping: Dict[str, str] = {}
    paths = [
        os.path.join(REPO_ROOT, "static", "i18n", "de.json"),
        os.path.join(REPO_ROOT, "static", "i18n", "en.json"),
    ]
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for key, val in data.items():
            if not key.startswith("ui.asset_class_"):
                continue
            canon = key.split("ui.asset_class_")[-1]
            if isinstance(val, str):
                mapping[val.strip().lower()] = canon

    # Add common provider-specific aliases that don't appear in ui asset class labels.
    mapping.update(ASSET_LABEL_ALIASES)
    return mapping


class FundScraper:
    def extract_all(self, html: str, base_url: str) -> Dict:
        """Return a dict of extracted values. Subclasses should override."""
        return {}
