# FundsPortfolio

[![CI/CD](https://github.com/LowFatMatt/FundsPortfolio/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/LowFatMatt/FundsPortfolio/actions)

**Overview**
FundsPortfolio is a Flask-based portfolio recommender for investment funds. It loads a fund database, asks a short questionnaire, and returns a diversified portfolio with explainability and a persistent `portfolio_id` you can later resume.

**What’s Implemented**
1. Questionnaire-driven recommendations with risk profiling and preference filters (ESG, ETF, region, theme).
2. Explainability output for each fund plus a decision trace of filters/relaxations.
3. A web UI for interactive users and a JSON API for machine access.
4. Dynamic preferred regions/themes derived from the fund database, refreshed when the database changes.

**Quick Start (Docker)**
1. `docker compose up --build -d`
2. Open `http://localhost:5000/`

**Quick Start (Local)**
1. `python -m pip install -r requirements.txt`
2. `PYTHONPATH=. python -m funds_portfolio.app`
3. Open `http://localhost:5000/`

**API Endpoints**
- `GET /health` → health check
- `GET /api/questionnaire` → questionnaire schema
- `POST /api/portfolio` → generate a portfolio
- `GET /api/portfolio/<portfolio_id>` → resume a portfolio

Example request:
```bash
curl -s -X POST http://localhost:5000/api/portfolio \
  -H "Content-Type: application/json" \
  -d '{
    "user_answers": {
      "investment_goal": "retirement",
      "investment_duration": "20_plus_years",
      "monthly_savings": "300_500",
      "investment_knowledge": "experienced",
      "risk_approach": "moderate",
      "loss_tolerance": "high_loss_tolerance",
      "esg_preference": "no_requirement",
      "etf_preference": "no_preference"
    }
  }'
```

**Data Sources**
- Fund database: `funds_database.json`
- Questionnaire schema: `preferences_schema.json`
- CSV inputs (for enrichment/import): `assets/data/`
- Notes/ideas: `notes/`

To (re)build the fund database from CSVs:
1. `python scripts/import_csv_funds.py` for a dry run
2. `python scripts/import_csv_funds.py --write` to write `funds_database.json`

**Where Portfolios Are Stored**
- Portfolios are written to `./portfolios/` when writable.
- If not writable, the app falls back to `/tmp/portfolios` and logs a warning.

**Tests and Linting**
- Tests: `python -m pytest`
- Lint: `python -m ruff check --select E,F,W .`


**Run CI Locally (Quick Check)**
- `make ci`
- `python -m ruff format .`
- `python -m ruff check .`
- `python -m pytest`

**Project Layout**
- `funds_portfolio/` → backend logic and Flask app
- `templates/` and `static/` → frontend UI
- `scripts/` → data utilities and ingestion tools

**License**
This is a prototype project and does not provide financial advice.


