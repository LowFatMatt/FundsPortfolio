"""Tests for Flask application"""

import pytest
from unittest.mock import MagicMock, patch

from funds_portfolio.app import create_app


@pytest.fixture
def app():
    """Create and configure test app"""
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


def test_health_check(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_questionnaire_endpoint(client):
    """Test questionnaire endpoint (stub)"""
    response = client.get("/api/questionnaire")
    assert response.status_code == 200


@patch("funds_portfolio.data.price_fetcher.yf.Ticker")
def test_create_portfolio_endpoint(mock_ticker, client):
    """Test portfolio creation endpoint with a mocked valid questionnaire response"""

    # Needs to be a valid response to pass validators and min 5 funds
    valid_answers = {
        "investment_goal": "retirement",
        "investment_duration": "20_plus_years",
        "monthly_savings": "300_500",
        "investment_knowledge": "experienced",
        "risk_approach": "moderate",
        "loss_tolerance": "high_loss_tolerance",
        "esg_preference": "no_requirement",
        "etf_preference": "no_preference",
    }

    # Mock yfinance to avoid any external calls
    mock_instance = MagicMock()
    mock_instance.history.return_value = MagicMock(empty=True)
    mock_ticker.return_value = mock_instance

    response = client.post("/api/portfolio", json={"user_answers": valid_answers})
    assert response.status_code == 201

    data = response.json
    assert "portfolio_id" in data
    assert "recommendations" in data
    assert "risk_profile" in data
    assert "portfolio_metrics" in data
    assert "explanations" in data
    assert "decision_trace" in data
    assert len(data["recommendations"]) >= 5


def test_create_portfolio_validation_error(client):
    """Missing required fields should return 400 with details"""
    invalid_answers = {"risk_approach": "moderate"}

    response = client.post("/api/portfolio", json={"user_answers": invalid_answers})
    assert response.status_code == 400
    data = response.json
    assert data["error"] == "Validation failed"
    assert "details" in data


def test_index_route(client):
    """Index page should return HTML even if template missing"""
    response = client.get("/")
    assert response.status_code == 200
    assert b"<html" in response.data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
