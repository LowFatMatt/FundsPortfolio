"""Tests for price fetcher"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from funds_portfolio.data.price_fetcher import PriceFetcher


@pytest.fixture
def sample_price_data():
    """Create a sample pandas dataframe mimicking yfinance output"""
    dates = pd.date_range(
        start="2020-01-01", periods=252 * 5, freq="B"
    )  # 5 years of business days

    # Create simple linear growth with some noise
    # ~10% annual return
    daily_growth_rate = 0.10 / 252
    rng = np.random.default_rng(42)
    noise = rng.normal(
        0, 0.01, len(dates)
    )  # Daily standard deviation of 1% (~15.8% annualized vol)

    returns = daily_growth_rate + noise

    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1 + r))

    prices = prices[1:]  # Drop initial value

    df = pd.DataFrame({"Close": prices}, index=dates)

    return df


class TestPriceFetcher:
    """Test PriceFetcher class"""

    @patch("funds_portfolio.data.price_fetcher.yf.Ticker")
    def test_fetch_prices(self, mock_ticker, sample_price_data):
        """Test fetching prices with yfinance mock"""
        # Setup mock
        mock_instance = MagicMock()
        mock_instance.history.return_value = sample_price_data
        mock_ticker.return_value = mock_instance

        fetcher = PriceFetcher(history_years=5)
        df = fetcher.fetch_prices("CSPX.AS")

        assert df is not None
        assert not df.empty
        assert "Close" in df.columns
        assert len(df) == len(sample_price_data)

        # Verify yf.Ticker was called with correct ticker
        mock_ticker.assert_called_with("CSPX.AS")
        mock_instance.history.assert_called_once()

    @patch("funds_portfolio.data.price_fetcher.yf.Ticker")
    def test_fetch_prices_empty(self, mock_ticker):
        """Test behavior when yfinance returns empty dataframe"""
        mock_instance = MagicMock()
        mock_instance.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_instance

        fetcher = PriceFetcher()
        df = fetcher.fetch_prices("INVALID")

        assert df is None

    def test_calculate_metrics(self, sample_price_data):
        """Test return and volatility computation"""
        fetcher = PriceFetcher()
        metrics = fetcher.calculate_metrics(sample_price_data)

        assert "annualized_return" in metrics
        assert "annualized_volatility" in metrics

        # Return should be positive and roughly around 10%
        # Volatitlity should be roughly around 15.8% (1% daily * sqrt(252))
        assert metrics["annualized_return"] > 0.0
        assert metrics["annualized_volatility"] > 0.0
        assert isinstance(metrics["annualized_return"], float)
        assert isinstance(metrics["annualized_volatility"], float)

    def test_calculate_metrics_empty(self):
        """Test calculation with empty data"""
        fetcher = PriceFetcher()

        metrics = fetcher.calculate_metrics(pd.DataFrame())
        assert metrics["annualized_return"] == 0.0
        assert metrics["annualized_volatility"] == 0.0

        metrics = fetcher.calculate_metrics(None)
        assert metrics["annualized_return"] == 0.0
        assert metrics["annualized_volatility"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
