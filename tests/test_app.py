"""Tests for Flask application"""

import pytest
from funds_portfolio.app import create_app


@pytest.fixture
def app():
    """Create and configure test app"""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


def test_health_check(client):
    """Test health endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_questionnaire_endpoint(client):
    """Test questionnaire endpoint (stub)"""
    response = client.get('/api/questionnaire')
    assert response.status_code == 200


from unittest.mock import patch, MagicMock

@patch('funds_portfolio.data.price_fetcher.yf.Ticker')
def test_create_portfolio_endpoint(mock_ticker, client):
    """Test portfolio creation endpoint with a mocked valid questionnaire response"""
    
    # Needs to be a valid response to pass validators and min 5 funds
    valid_answers = {
        'investment_goal': 'retirement',
        'investment_duration': '20_plus_years',
        'monthly_savings': '300_500',
        'investment_knowledge': 'experienced',
        'risk_approach': 'moderate',
        'loss_tolerance': 'high_loss_tolerance'
    }
    
    # Mock yfinance to always return some positive growth so Sharpe is computed
    import pandas as pd
    import numpy as np
    
    dates = pd.date_range(start='2020-01-01', periods=252*5, freq='B')
    prices = [100.0]
    for _ in range(len(dates)-1):
        prices.append(prices[-1] * (1 + 0.10/252 + np.random.normal(0, 0.01)))
        
    df = pd.DataFrame({'Close': prices}, index=dates)
    
    mock_instance = MagicMock()
    mock_instance.history.return_value = df
    mock_ticker.return_value = mock_instance
    
    response = client.post('/api/portfolio', json={"user_answers": valid_answers})
    assert response.status_code == 201
    
    data = response.json
    assert "portfolio_id" in data
    assert "recommendations" in data
    assert len(data["recommendations"]) >= 5


def test_index_route(client):
    """Index page should return HTML even if template missing"""
    response = client.get('/')
    assert response.status_code == 200
    assert b"<html" in response.data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
