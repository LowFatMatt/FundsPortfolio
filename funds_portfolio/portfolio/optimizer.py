"""
Portfolio Optimizer - Generates fund allocations based on risk profile
"""

from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """Assigns weights to funds based on risk profiles."""

    def __init__(self):
        # Target equity allocation based on risk level 1 (Conservative)
        # through 4 (Aggressive)
        self.risk_allocations = {
            1: {"equity": 0.0, "bond": 1.0},
            2: {"equity": 0.4, "bond": 0.6},
            3: {"equity": 0.7, "bond": 0.3},
            4: {"equity": 0.9, "bond": 0.1},
        }

    def _determine_risk_level(self, user_answers: Dict) -> Tuple[int, bool]:
        """
        Extract numeric risk level (1-4).
        If an old API string is used, map it (e.g. moderate -> 3).
        """
        approach = str(user_answers.get("risk_approach", "")).lower()
        if approach == "conservative" or approach == "1":
            return 1, False
        if approach == "moderate_low" or approach == "2":
            return 2, False
        if approach == "moderate" or approach == "3":
            return 3, False
        if approach == "aggressive" or approach == "4":
            return 4, False

        # Default fallback
        logger.warning(
            "Unrecognized risk approach '%s', defaulting to 2 (moderate low)", approach
        )
        return 2, True

    def optimize_portfolio(
        self, user_answers: Dict, enriched_funds: List[Dict]
    ) -> Tuple[List[Dict], Dict]:
        """
        Distribute weights across the top available funds based on risk mapping.

        Args:
            user_answers: Questionnaire responses determining risk tolerance.
            enriched_funds: List of funds (expected to be ranked by Sharpe Ratio).

        Returns:
            Tuple containing:
            - List of recommendations with 'allocation_percent' added.
            - Dictionary of optimizer metadata (e.g. used_fallback_risk flag).
        """
        if not enriched_funds:
            logger.warning("No funds to optimize.")
            return []

        risk_level, is_fallback = self._determine_risk_level(user_answers)
        target_allocation = self.risk_allocations[risk_level]

        # Separate into equity and bonds (treating everything else as
        # bond/conservative for MVP)
        equities = [
            f for f in enriched_funds if f.get("asset_class", "").lower() == "equity"
        ]
        bonds = [
            f for f in enriched_funds if f.get("asset_class", "").lower() != "equity"
        ]

        recommendations = []
        optimizer_metadata = {"used_fallback_risk": is_fallback}

        # Distribute equity portion among top 5 equities
        equity_share = target_allocation["equity"] * 100
        if equities and equity_share > 0:
            top_equities = equities[:5]
            per_fund_share = equity_share / len(top_equities)
            for f in top_equities:
                rec = dict(f)
                rec["allocation_percent"] = round(per_fund_share, 2)
                rec["rationale"] = (
                    f"Top Sharpe Equity component (Risk level {risk_level})"
                )
                recommendations.append(rec)

        # Distribute bond portion among top 5 bonds
        bond_share = target_allocation["bond"] * 100
        if bonds and bond_share > 0:
            top_bonds = bonds[:5]
            per_fund_share = bond_share / len(top_bonds)
            for f in top_bonds:
                rec = dict(f)
                rec["allocation_percent"] = round(per_fund_share, 2)
                rec["rationale"] = (
                    f"Top Sharpe Fixed Income component (Risk level {risk_level})"
                )
                recommendations.append(rec)

        # Fix minor rounding errors so it sums to 100
        if recommendations:
            total = sum(r["allocation_percent"] for r in recommendations)
            diff = 100.0 - total
            if abs(diff) > 0.001:
                # Add difference to the first recommendation
                recommendations[0]["allocation_percent"] = round(
                    recommendations[0]["allocation_percent"] + diff, 2
                )

        return recommendations, optimizer_metadata
