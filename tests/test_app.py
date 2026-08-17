"""Tests for Flask application"""

import pytest
from unittest.mock import MagicMock, patch

from funds_portfolio.app import create_app
from funds_portfolio.data.providers import reset_provider
from funds_portfolio.data.fund_manager import reset_fund_manager


@pytest.fixture
def app(monkeypatch):
    """Create and configure test app.

    Force CUSTOMER=general so the test runs against the broad ETF-rich
    universe, not whichever customer is currently activated at repo root.
    Keeps assertions about fund counts and weighted-fee caps stable
    across customer-profile switches.
    """
    monkeypatch.setenv("CUSTOMER", "general")
    reset_provider()
    reset_fund_manager()
    app = create_app()
    app.config["TESTING"] = True
    yield app
    reset_provider()
    reset_fund_manager()


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
        "risk_approach": "moderate",
        "esg_preference": "NONE",
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
    """Invalid answer values should return 400 with details.

    Missing fields are now auto-filled by apply_defaults, so a validation
    error is only raised for an explicitly invalid value.
    """
    invalid_answers = {"risk_approach": "not_a_real_option"}

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


def test_flow_definition_endpoint(client):
    """Flow-Mode wizard configs are served as JSON with a `steps` array."""
    for variant in ("A", "B"):
        response = client.get(f"/flows/variant{variant}.json")
        assert response.status_code == 200
        data = response.json
        assert isinstance(data.get("steps"), list) and data["steps"]


@patch("funds_portfolio.data.price_fetcher.yf.Ticker")
def test_quick_flow_equivalence(mock_ticker, client):
    """Quick-Mode and Flow-Mode hit the same endpoint and must yield the same
    portfolio for the same logic-relevant inputs.

    The Flow payload carries extra commercial fields (anlageziel, beitrag,
    produkt, …) that the engine does not consume. This proves both that the API
    is mode-agnostic and that the extras never influence the recommendation.
    See MODES.md §1.
    """
    mock_instance = MagicMock()
    mock_instance.history.return_value = MagicMock(empty=True)
    mock_ticker.return_value = mock_instance

    logic_answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["europe"],
        "preferred_themes": ["none"],
    }
    flow_answers = {
        **logic_answers,
        "anlageziel": "altersvorsorge",
        "beitrag": "beides",
        "beitragLaufend": "150",
        "beitragEinmalig": "10000",
        "produkt": "FondsRente Vario",
        "aktivitaet": "Aktiv-Kunde",
    }

    quick = client.post("/api/portfolio", json={"user_answers": logic_answers})
    flow = client.post("/api/portfolio", json={"user_answers": flow_answers})
    assert quick.status_code == 201 and flow.status_code == 201

    def fingerprint(resp):
        data = resp.json
        recs = [(r["isin"], r["allocation_percent"]) for r in data["recommendations"]]
        return data["risk_profile"], recs

    assert fingerprint(quick) == fingerprint(flow)


@patch("funds_portfolio.data.price_fetcher.yf.Ticker")
def test_decision_trace_stages(mock_ticker, client):
    """The decision trace exposes the ranking, selection and allocation stages
    so the recommendation is transparent (see MODES.md §1)."""
    mock_instance = MagicMock()
    mock_instance.history.return_value = MagicMock(empty=True)
    mock_ticker.return_value = mock_instance

    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": ["europe", "north_america"],
        "preferred_themes": ["technology"],
    }
    resp = client.post("/api/portfolio", json={"user_answers": answers})
    assert resp.status_code == 201
    trace = resp.json["decision_trace"]

    # Ranking stage: bounded to top_k, each candidate carries a score breakdown
    ranking = trace["ranking"]
    assert ranking["formula"] == {"sharpe": 5, "mdd": 3, "ter": 2}
    assert 0 < len(ranking["candidates"]) <= ranking["top_k"]
    valid_status = {
        "selected",
        "selected_pass1_coverage",
        "skipped_provider_cap",
        "skipped_category_cap",
        "skipped_theme_quota",
        "skipped_region_quota",
        "not_reached",
    }
    for c in ranking["candidates"]:
        assert c["status"] in valid_status
        assert {"rank", "isin", "base", "boosts", "final"} <= set(c)
    # Exactly the recommended funds are marked "selected*"
    selected = [
        c for c in ranking["candidates"] if str(c["status"]).startswith("selected")
    ]
    assert len(selected) == len(resp.json["recommendations"])

    # Selection + allocation stages present
    assert "events" in trace["selection"] and "caps" in trace["selection"]
    alloc = trace["allocation"]
    assert "satellite_cap_applied" in alloc
    assert len(alloc["funds"]) == len(resp.json["recommendations"])
    for fund in alloc["funds"]:
        assert fund["class"] in {"core", "satellite"}
        assert {"inv_vol_raw", "tier_bounds", "after_clip", "final_weight"} <= set(fund)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
