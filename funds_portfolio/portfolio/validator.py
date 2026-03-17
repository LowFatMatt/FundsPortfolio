"""
Portfolio Validator - Validates a generated portfolio against business rules
"""

from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class PortfolioValidator:
    """Validates portfolios against rules (diversification, fee caps, etc.)."""

    def __init__(self, min_funds: int = 5, max_fee: float = 0.50):
        self.min_funds = min_funds
        self.max_fee = max_fee

    def validate_recommendations(
        self, recommendations: List[Dict]
    ) -> Tuple[bool, List[str]]:
        """
        Check if the proposed allocations meet rules.

        Args:
            recommendations: List of dictionaries with "allocation_percent",
            "yearly_fee", etc.

        Returns:
            (is_valid, list of error strings)
        """
        errors = []

        if not recommendations:
            return False, ["No funds recommended"]

        if len(recommendations) < self.min_funds:
            errors.append(
                "Portfolio lacks diversification: "
                f"{len(recommendations)} funds (minimum {self.min_funds})"
            )

        total_allocation = sum(
            r.get("allocation_percent", 0.0) for r in recommendations
        )
        if abs(total_allocation - 100.0) > 0.01:
            errors.append(f"Total allocation is {total_allocation}%, must be 100%")

        # Calculate weighted average fee
        weighted_fee = sum(
            (r.get("allocation_percent", 0) / 100.0) * r.get("yearly_fee", 0.0)
            for r in recommendations
        )

        if weighted_fee > self.max_fee:
            errors.append(
                "Expected fee is "
                f"{weighted_fee:.2f}%, exceeding maximum {self.max_fee:.2f}%"
            )

        is_valid = len(errors) == 0
        return is_valid, errors
