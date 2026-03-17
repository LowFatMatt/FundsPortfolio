"""
Fund database manager - loads and caches funds_database.json
"""

import json
import os
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class FundManager:
    """Manages fund database - loads, caches, and provides fund lookups"""

    def __init__(self, db_path: str = "/app/funds_database.json"):
        """
        Initialize FundManager with path to funds database.

        Args:
            db_path: Path to funds_database.json file.  When running on the
                     host (not in Docker) the container path may not exist,
                     so we fall back to a file in the current working
                     directory.
        """
        if not os.path.exists(db_path):
            # try relative path in project root
            alt = os.path.join(os.getcwd(), "funds_database.json")
            if os.path.exists(alt):
                logger.debug("using fallback funds database path %s", alt)
                db_path = alt
        self.db_path = db_path
        self._funds_cache: Optional[List[Dict]] = None
        self._metadata: Optional[Dict] = None
        self.load_funds()

    def load_funds(self) -> bool:
        """
        Load funds from JSON file and cache in memory.

        Returns:
            True if load successful, False otherwise
        """
        try:
            if not os.path.exists(self.db_path):
                logger.error("Fund database not found at %s", self.db_path)
                return False

            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._funds_cache = data.get("funds_database", [])
            self._metadata = data.get("metadata", {})

            logger.info("Loaded %d funds from %s", len(self._funds_cache), self.db_path)
            return True

        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load funds database: %s", e)
            return False

    def get_all_funds(self) -> List[Dict]:
        """
        Get all funds from cache.

        Returns:
            List of fund dictionaries
        """
        if self._funds_cache is None:
            return []
        return self._funds_cache

    def get_fund_by_isin(self, isin: str) -> Optional[Dict]:
        """
        Get a single fund by ISIN.

        Args:
            isin: 12-character ISIN code (e.g., 'IE00B4L5Y983')

        Returns:
            Fund dictionary if found, None otherwise
        """
        if self._funds_cache is None:
            return None

        for fund in self._funds_cache:
            if fund.get("isin", "").upper() == isin.upper():
                return fund

        return None

    def get_funds_by_risk_level(self, risk_level: int) -> List[Dict]:
        """
        Get all funds matching a risk level (1-5).

        Args:
            risk_level: Risk level 1 (conservative) to 5 (aggressive)

        Returns:
            List of matching fund dictionaries
        """
        if self._funds_cache is None:
            return []

        return [f for f in self._funds_cache if f.get("risk_level") == risk_level]

    def get_funds_by_asset_class(self, asset_class: str) -> List[Dict]:
        """
        Get all funds matching an asset class.

        Args:
            asset_class: 'equity', 'bond', 'mixed', etc.

        Returns:
            List of matching fund dictionaries
        """
        if self._funds_cache is None:
            return []

        return [
            f
            for f in self._funds_cache
            if f.get("asset_class", "").lower() == asset_class.lower()
        ]

    def get_funds_by_category(self, category: str) -> List[Dict]:
        """
        Get all funds matching a category.

        Args:
            category: Category ID (e.g., 'us_equity', 'government_bonds')

        Returns:
            List of matching fund dictionaries
        """
        if self._funds_cache is None:
            return []

        result = []
        for fund in self._funds_cache:
            if category in fund.get("categories", []):
                result.append(fund)

        return result

    def get_metadata(self) -> Dict:
        """
        Get database metadata.

        Returns:
            Metadata dictionary
        """
        return self._metadata or {}

    def is_loaded(self) -> bool:
        """
        Check if fund database is loaded.

        Returns:
            True if funds are loaded, False otherwise
        """
        return self._funds_cache is not None and len(self._funds_cache) > 0

    def save_funds(self) -> bool:
        """
        Save the current funds cache and metadata back to the JSON file.

        Returns:
            True if save successful, False otherwise.
        """
        if self._funds_cache is None:
            logger.error("Cannot save funds; cache is not loaded.")
            return False

        try:
            data = {
                "funds_database": self._funds_cache,
                "metadata": self._metadata or {},
            }
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logger.info("Saved %d funds to %s", len(self._funds_cache), self.db_path)
            return True
        except IOError as e:
            logger.error("Failed to save funds database: %s", e)
            return False

    def add_fund(self, fund_data: Dict) -> bool:
        """
        Add a new fund to the database.

        Args:
            fund_data: Dictionary containing fund details. Must include an 'isin'.

        Returns:
            True if added successfully, False if ISIN already exists or invalid data.
        """
        if not fund_data.get("isin"):
            logger.error("Cannot add fund without ISIN.")
            return False

        existing = self.get_fund_by_isin(fund_data["isin"])
        if existing is not None:
            logger.error("Fund with ISIN %s already exists.", fund_data["isin"])
            return False

        if self._funds_cache is None:
            self._funds_cache = []

        self._funds_cache.append(fund_data)
        logger.info("Added new fund with ISIN %s", fund_data["isin"])
        return self.save_funds()

    def update_fund(self, isin: str, updates: Dict) -> bool:
        """
        Update an existing fund.

        Args:
            isin: ISIN of the fund to update.
            updates: Dictionary of key-value pairs to update.

        Returns:
            True if updated successfully, False if not found.
        """
        if self._funds_cache is None:
            return False

        for i, fund in enumerate(self._funds_cache):
            if fund.get("isin", "").upper() == isin.upper():
                # apply updates
                self._funds_cache[i].update(updates)
                # optionally ensure ISIN is not altered
                self._funds_cache[i]["isin"] = fund.get("isin", "").upper()
                logger.info("Updated fund with ISIN %s", isin)
                return self.save_funds()

        logger.error("Fund with ISIN %s not found for update.", isin)
        return False

    def delete_fund(self, isin: str) -> bool:
        """
        Delete a fund from the database.

        Args:
            isin: ISIN of the fund to delete.

        Returns:
            True if deleted successfully, False if not found.
        """
        if self._funds_cache is None:
            return False

        initial_len = len(self._funds_cache)
        self._funds_cache = [
            f for f in self._funds_cache if f.get("isin", "").upper() != isin.upper()
        ]

        if len(self._funds_cache) < initial_len:
            logger.info("Deleted fund with ISIN %s", isin)
            return self.save_funds()

        logger.error("Fund with ISIN %s not found for deletion.", isin)
        return False


# Singleton instance for application-wide use
_fund_manager_instance = None


def get_fund_manager(db_path: str = "/app/funds_database.json") -> FundManager:
    """
    Get or create the global FundManager instance.

    Args:
        db_path: Path to funds_database.json (used on first call)

    Returns:
        FundManager singleton instance
    """
    global _fund_manager_instance
    if _fund_manager_instance is None:
        _fund_manager_instance = FundManager(db_path)
    return _fund_manager_instance
