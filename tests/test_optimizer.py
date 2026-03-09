"""Tests for optimizer engine"""

import pytest
from funds_portfolio.portfolio.optimizer import PortfolioOptimizer


class TestPortfolioOptimizer:
    """Test PortfolioOptimizer allocation logic"""
    
    @pytest.fixture
    def sample_funds(self):
        return [
            {"isin": "E1", "name": "Eq1", "asset_class": "equity", "sharpe_ratio": 1.5},
            {"isin": "E2", "name": "Eq2", "asset_class": "equity", "sharpe_ratio": 1.4},
            {"isin": "E3", "name": "Eq3", "asset_class": "equity", "sharpe_ratio": 1.3},
            {"isin": "E4", "name": "Eq4", "asset_class": "equity", "sharpe_ratio": 1.2},
            {"isin": "E5", "name": "Eq5", "asset_class": "equity", "sharpe_ratio": 1.1},
            {"isin": "E6", "name": "Eq6", "asset_class": "equity", "sharpe_ratio": 1.0}, # Should be excluded from top 5
            {"isin": "B1", "name": "Bd1", "asset_class": "bond", "sharpe_ratio": 0.8},
            {"isin": "B2", "name": "Bd2", "asset_class": "bond", "sharpe_ratio": 0.7},
            {"isin": "B3", "name": "Bd3", "asset_class": "bond", "sharpe_ratio": 0.6},
        ]
        
    def test_determine_risk_level(self):
        opt = PortfolioOptimizer()
        assert opt._determine_risk_level({'risk_approach': 'conservative'}) == 1
        assert opt._determine_risk_level({'risk_approach': '1'}) == 1
        assert opt._determine_risk_level({'risk_approach': 'aggressive'}) == 4
        # Fallback test
        assert opt._determine_risk_level({'risk_approach': 'unknown'}) == 2
        
    def test_conservative_allocation(self, sample_funds):
        opt = PortfolioOptimizer()
        recs = opt.optimize_portfolio({'risk_approach': 'conservative'}, sample_funds)
        
        # Total should be 100
        total = sum(r['allocation_percent'] for r in recs)
        assert abs(total - 100.0) < 0.01
        
        # With conservative (1), it should be 100% bonds
        # There are 3 bonds, so ~33.33% each
        assert len(recs) == 3
        for r in recs:
            assert r['asset_class'] == 'bond'
            assert abs(r['allocation_percent'] - 33.33) < 0.1
            
    def test_aggressive_allocation(self, sample_funds):
        opt = PortfolioOptimizer()
        recs = opt.optimize_portfolio({'risk_approach': 'aggressive'}, sample_funds)
        
        # Aggressive (4) is 90% equity and 10% bond
        # We cap at top 5 equities. 90 / 5 = 18% each
        # And top 3 bonds (all available): 10 / 3 = 3.33% each
        total = sum(r['allocation_percent'] for r in recs)
        assert abs(total - 100.0) < 0.01
        
        equities = [r for r in recs if r['asset_class'] == 'equity']
        bonds = [r for r in recs if r['asset_class'] == 'bond']
        
        assert len(equities) == 5
        assert len(bonds) == 3
        
        eq_total = sum(r['allocation_percent'] for r in equities)
        bd_total = sum(r['allocation_percent'] for r in bonds)
        
        assert abs(eq_total - 90.0) < 0.02
        assert abs(bd_total - 10.0) < 0.02

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
