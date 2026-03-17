"""Tests for validator component"""

import pytest
from funds_portfolio.portfolio.validator import PortfolioValidator


class TestPortfolioValidator:
    """Test PortfolioValidator rules"""

    def test_valid_portfolio(self):
        val = PortfolioValidator(min_funds=3, max_fee=0.50)

        recs = [
            {"allocation_percent": 40.0, "yearly_fee": 0.10},
            {"allocation_percent": 30.0, "yearly_fee": 0.20},
            {"allocation_percent": 30.0, "yearly_fee": 0.30},
        ]

        # Weighted fee: (0.4 * 0.1) + (0.3 * 0.2) + (0.3 * 0.3) =
        # 0.04 + 0.06 + 0.09 = 0.19%
        is_valid, errors = val.validate_recommendations(recs)

        assert is_valid
        assert len(errors) == 0

    def test_invalid_allocation_sum(self):
        val = PortfolioValidator()

        recs = [
            {"allocation_percent": 50.0},
            {"allocation_percent": 40.0},
        ]

        is_valid, errors = val.validate_recommendations(recs)
        assert not is_valid
        assert any("must be 100" in e for e in errors)

    def test_insufficient_diversification(self):
        val = PortfolioValidator(min_funds=5)

        recs = [
            {"allocation_percent": 50.0},
            {"allocation_percent": 50.0},
        ]

        is_valid, errors = val.validate_recommendations(recs)
        assert not is_valid
        assert any("diversification" in e for e in errors)

    def test_high_fee(self):
        val = PortfolioValidator(min_funds=2, max_fee=0.50)

        recs = [
            {"allocation_percent": 50.0, "yearly_fee": 0.80},
            {"allocation_percent": 50.0, "yearly_fee": 0.60},
        ]

        # Weighted fee: 0.70% > 0.50%
        is_valid, errors = val.validate_recommendations(recs)
        assert not is_valid
        assert any("exceeding maximum" in e for e in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
