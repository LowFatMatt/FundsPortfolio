"""
Calculates risk-adjusted metrics like the Sharpe Ratio for a list of funds.
"""

from typing import List, Dict, Optional
import logging
from funds_portfolio.data.price_fetcher import PriceFetcher

logger = logging.getLogger(__name__)


class PortfolioCalculator:
    """Calculates metrics like Sharpe Ratio and ranks funds."""
    
    def __init__(self, risk_free_rate: float = 0.02, price_fetcher: Optional[PriceFetcher] = None):
        """
        Args:
            risk_free_rate: The benchmark risk-free rate (e.g., 0.02 for 2%)
            price_fetcher: Dependency injected price fetcher
        """
        self.risk_free_rate = risk_free_rate
        self.price_fetcher = price_fetcher or PriceFetcher()

    def calculate_sharpe_ratio(self, annualized_return: float, annualized_volatility: float) -> float:
        """
        Calculate the Sharpe Ratio.
        
        Formula: (Return - Risk-Free Rate) / Volatility
        """
        if annualized_volatility <= 0:
            return 0.0
            
        return (annualized_return - self.risk_free_rate) / annualized_volatility

    def enrich_and_rank_funds(self, funds: List[Dict]) -> List[Dict]:
        """
        Calculate metrics for all given funds and rank them descending by Sharpe Ratio.
        
        Args:
            funds: List of fund dictionaries (must contain 'isin')
            
        Returns:
            A new sorted list of enriched fund dictionaries.
        """
        enriched_funds = []
        
        for fund in funds:
            # We copy to avoid mutating the original dict unexpectedly
            fund_copy = dict(fund)
            isin = fund_copy.get('isin')
            
            if not isin:
                logger.warning("Fund missing ISIN, skipping in ranking.")
                continue
                
            metrics = self.price_fetcher.get_fund_metrics(isin)
            
            if metrics:
                fund_copy['annualized_return'] = metrics['annualized_return']
                fund_copy['annualized_volatility'] = metrics['annualized_volatility']
                fund_copy['sharpe_ratio'] = self.calculate_sharpe_ratio(
                    metrics['annualized_return'], 
                    metrics['annualized_volatility']
                )
            else:
                # If we can't fetch metrics, penalize the fund with zeroes
                fund_copy['annualized_return'] = 0.0
                fund_copy['annualized_volatility'] = 0.0
                fund_copy['sharpe_ratio'] = 0.0
                
            enriched_funds.append(fund_copy)
            
        # Sort descending by sharpe ratio
        enriched_funds.sort(key=lambda x: x.get('sharpe_ratio', 0.0), reverse=True)
        return enriched_funds
