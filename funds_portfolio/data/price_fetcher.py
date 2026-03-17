"""
Price Fetcher - retrieves historical performance data using yfinance
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PriceFetcher:
    """Fetches historical prices and calculates performance metrics"""

    def __init__(self, history_years: int = 5):
        self.history_years = history_years

    def fetch_prices(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical daily closing prices.

        Args:
            ticker: The yfinance compatible ticker symbol

        Returns:
            DataFrame with Date index and 'Close' column, or None on failure.
        """
        try:
            logger.info("Fetching price history for %s", ticker)

            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.history_years * 365.25)

            # yfinance expects YYYY-MM-DD
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            fund = yf.Ticker(ticker)
            history = fund.history(start=start_str, end=end_str)

            if history.empty:
                logger.warning("No price history found for %s", ticker)
                return None

            # Just keep the Close prices
            df = history[["Close"]].copy()
            df.index = df.index.tz_localize(None)  # Remove tz for easier handling
            return df

        except Exception as e:
            logger.error("Error fetching prices for %s: %s", ticker, e)
            return None

    def calculate_metrics(self, prices: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate annualized return and volatility from daily prices.

        Args:
            prices: DataFrame with 'Close' column and Date index

        Returns:
            Dictionary with 'annualized_return' and 'annualized_volatility'
        """
        if prices is None or prices.empty or len(prices) < 2:
            return {"annualized_return": 0.0, "annualized_volatility": 0.0}

        # Calculate daily returns
        daily_returns = prices["Close"].pct_change().dropna()

        if len(daily_returns) == 0:
            return {"annualized_return": 0.0, "annualized_volatility": 0.0}

        # Annualize the returns
        # Usually 252 trading days in a year
        trading_days = 252

        # Compound logic for total return, then annualize
        mean_daily_return = daily_returns.mean()
        annualized_return = (1 + mean_daily_return) ** trading_days - 1

        # Standard deviation for volatility
        daily_volatility = daily_returns.std()
        annualized_volatility = daily_volatility * np.sqrt(trading_days)

        return {
            "annualized_return": float(annualized_return),
            "annualized_volatility": float(annualized_volatility),
        }

    def get_fund_metrics(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Convenience method to fetch prices and calculate metrics in one step.
        """
        prices = self.fetch_prices(ticker)
        if prices is not None:
            return self.calculate_metrics(prices)
        return None
