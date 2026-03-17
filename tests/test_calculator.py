"""Tests for calculation engine"""

import pytest
from unittest.mock import MagicMock
from funds_portfolio.portfolio.calculator import PortfolioCalculator


class TestPortfolioCalculator:
    """Test PortfolioCalculator metrics and ranking"""

    def test_calculate_sharpe_ratio(self):
        calc = PortfolioCalculator(risk_free_rate=0.02)

        # (0.10 - 0.02) / 0.15 = 0.08 / 0.15 = 0.5333...
        sharpe = calc.calculate_sharpe_ratio(0.10, 0.15)
        assert abs(sharpe - 0.5333) < 0.001

        # Handle zero volatility gracefully
        sharpe_zero_vol = calc.calculate_sharpe_ratio(0.10, 0.0)
        assert sharpe_zero_vol == 0.0

        # Handle negative return
        sharpe_neg = calc.calculate_sharpe_ratio(-0.05, 0.15)
        assert sharpe_neg < 0.0

    def test_enrich_and_rank_funds(self):
        # Setup mock fetcher
        mock_fetcher = MagicMock()

        # We'll return deterministic metrics for our test ISINs
        def mock_get_metrics(isin):
            if isin == "FUND1":
                return {
                    "annualized_return": 0.12,
                    "annualized_volatility": 0.10,
                }  # Sharpe ~1.0
            if isin == "FUND2":
                return {
                    "annualized_return": 0.06,
                    "annualized_volatility": 0.05,
                }  # Sharpe ~0.8
            if isin == "FUND3":
                return {
                    "annualized_return": 0.08,
                    "annualized_volatility": 0.20,
                }  # Sharpe ~0.3
            return None

        mock_fetcher.get_fund_metrics.side_effect = mock_get_metrics

        calc = PortfolioCalculator(risk_free_rate=0.02, price_fetcher=mock_fetcher)

        # Test basic ranking
        funds = [
            {"isin": "FUND2", "name": "Safe Fund"},
            {"isin": "FUND3", "name": "Volatile Fund"},
            {"isin": "FUND1", "name": "Great Fund"},
            {"isin": "MISSING_DATA", "name": "Unknown"},
        ]

        ranked = calc.enrich_and_rank_funds(funds)

        # Expected order by Sharpe: FUND1, FUND2, FUND3, MISSING_DATA (zero)
        assert len(ranked) == 4
        assert ranked[0]["isin"] == "FUND1"
        assert ranked[1]["isin"] == "FUND2"
        assert ranked[2]["isin"] == "FUND3"
        assert ranked[3]["isin"] == "MISSING_DATA"

        # Ensure metrics were attached
        assert ranked[0]["sharpe_ratio"] > 0.99
        assert ranked[1]["sharpe_ratio"] > 0.79
        assert ranked[2]["sharpe_ratio"] > 0.29
        assert ranked[3]["sharpe_ratio"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
