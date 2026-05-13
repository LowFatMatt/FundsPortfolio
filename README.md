# FundsPortfolio

[![CI/CD](https://github.com/LowFatMatt/FundsPortfolio/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/LowFatMatt/FundsPortfolio/actions)

**Overview**
FundsPortfolio is a Flask-based portfolio recommender for investment funds. It loads a per-customer fund universe, asks a short questionnaire, and returns a diversified portfolio with explainability, performance/volatility charts, and a persistent `portfolio_id` you can later resume.

**What's Implemented**
1. Questionnaire-driven recommendations with risk profiling and preference filters (ESG, ETF, region, theme).
2. Explainability output for each fund plus a decision trace of filters/relaxations.
3. A Material-3-styled web UI: Summary tab with asset-class & region donut charts, Preferences tab, Performance tab with NAV chart + stress-period overlay toggles + period selector + per-period returns table, Volatility tab with vol/Sharpe/MDD bar chart and table.
4. Dynamic preferred regions/themes derived from the fund database, refreshed when the database changes.
5. **Data-provider abstraction** ([funds_portfolio/data/providers/](funds_portfolio/data/providers/)) — runtime is cache-first / read-only; scrapers run offline and write JSON files. Switching customers = a config / env-var change.
6. **Per-ISIN time-series data** in [data/funds/](data/funds/) — NAV history (monthly, rebased to 100), per-period returns, volatility, Sharpe ratios, max drawdown, asset-class breakdown, top holdings. Populated by [scripts/sync_factsheetslive.py](scripts/sync_factsheetslive.py).
7. **Customer-specific fund universes** under [data/customers/](data/customers/) — current profiles: `general` (197-fund accumulated catalog) and `provinzial_nord` (127-fund customer-curated universe). Selected via `CUSTOMER` env var or [scripts/select_customer.py](scripts/select_customer.py).
8. EN/DE i18n across UI, decision trace, and stress-period labels.

**Quick Start (Docker)**
1. `docker compose up --build -d`
2. Open `http://localhost:5000/`

**Quick Start (Local)**
1. `python -m pip install -r requirements.txt`
2. `PYTHONPATH=. python -m funds_portfolio.app`
3. Open `http://localhost:5000/`

**API Endpoints**

Core (Phase 1):
- `GET /health` → health check
- `GET /api/questionnaire` → questionnaire schema
- `POST /api/portfolio` → generate a portfolio
- `GET /api/portfolio/<portfolio_id>` → resume a portfolio
- `GET /api/funds` → all funds in the active catalog (debugging)

Phase 2 (charts, breakdowns, system state):
- `GET /api/funds/<isin>/performance` → per-period returns + monthly NAV series
- `GET /api/funds/<isin>/risk` → volatility + Sharpe + max drawdown (1Y / 3Y / 5Y)
- `GET /api/funds/<isin>/breakdown` → asset-class breakdown + top 10 holdings
- `GET /api/portfolio/<id>/performance?from=&to=` → weighted portfolio NAV vs. benchmark (clip-to-shortest-history policy)
- `GET /api/portfolio/<id>/breakdown` → portfolio-weighted asset-class & region rollups
- `GET /api/config/stress-periods` → stress-period overlay config for the Performance chart
- `GET /api/config/benchmarks` → app-level benchmark catalog
- `GET /api/data/health` → provider info, fund count, time-series coverage, last refresh

**Response Fields (POST /api/portfolio)**
- `risk_profile`
- `portfolio_metrics` (e.g., `weighted_fee`, `srri_proxy`, exposures)
- `explanations` (`summary`, `per_fund`)
- `decision_trace` (`filters`, `relaxations`, `used_fallback_risk`)
- Each recommendation also carries `asset_class_breakdown`, `region_breakdown`, `benchmark_id` (Phase 2, schema v2, nullable).

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
- Active fund catalog: `funds_database.json` at repo root (a copy of the active customer profile; managed by `scripts/select_customer.py`).
- Customer catalogs: `data/customers/{customer_id}/funds_database.json`.
- Per-ISIN time series: `data/funds/{ISIN}.json` (one per fund; written by the scraper).
- App-level config: `data/benchmarks.json`, `data/stress_periods.json`, `data_sources.yaml`.
- Questionnaire schema: `preferences_schema.json` / `preferences_schema_DE.json`.
- CSV inputs (for legacy enrichment): `assets/data/`.
- Notes / ISIN lists / TSV exports: `notes/`.

To (re)build a customer catalog from a TSV / ISIN list:
1. Populate per-ISIN files (one-time, then re-run weekly):
   `python scripts/sync_factsheetslive.py --isin-file notes/Provi-ISINs.txt`
2. Build the customer catalog:
   `python scripts/build_customer_catalog.py --customer provinzial_nord --source notes/Provi-Listing.tsv`
3. Activate it:
   `python scripts/select_customer.py provinzial_nord`

To switch between customers at runtime without touching the active file:
`CUSTOMER=general flask run` (provider factory honours the env var with fallback to repo-root `funds_database.json`).

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
  - `data/providers/` → DataProvider abstraction (Phase 2)
  - `config/stress_periods.py` → overlay config loader
  - `portfolio/aggregator.py` → portfolio-level NAV + breakdown rollups
- `templates/` and `static/` → frontend UI (M3 design tokens, Chart.js loaded lazily from CDN via `static/js/charts.js`)
- `scripts/` → data utilities and ingestion tools (factsheetslive sync, customer-catalog build/select)
- `data/customers/{id}/` → per-customer fund catalogs (Phase 2.5)
- `data/funds/{ISIN}.json` → per-ISIN scraped time-series (Phase 2)
- `data/benchmarks.json`, `data/stress_periods.json` → chart config

**License**
This is a prototype project and does not provide financial advice.




