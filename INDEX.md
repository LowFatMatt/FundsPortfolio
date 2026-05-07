# FundsPortfolio — Documentation Index

**Status:** Working MVP — questionnaire-driven fund recommendation engine, fully implemented.

---

## What's Built

| Component | File(s) | Notes |
|-----------|---------|-------|
| Flask app & API | `funds_portfolio/app.py` | All endpoints live here |
| Decision engine | `funds_portfolio/portfolio/decision_engine.py` | Filter → score → select → allocate |
| Portfolio optimizer | `funds_portfolio/portfolio/optimizer.py` | Weight allocation by risk profile |
| Sharpe calculator | `funds_portfolio/portfolio/calculator.py` | Risk-adjusted return scoring |
| Validator | `funds_portfolio/portfolio/validator.py` | Diversification, fee, count checks |
| Fund data loader | `funds_portfolio/data/fund_manager.py` | Loads `funds_database.json` |
| Price fetcher | `funds_portfolio/data/price_fetcher.py` | yfinance wrapper |
| Questionnaire loader | `funds_portfolio/questionnaire/loader.py` | Loads & validates user answers |
| Portfolio model | `funds_portfolio/models/portfolio.py` | UUID persistence to disk |
| Web UI | `templates/index.html` + `static/` | Questionnaire form + results display |
| Branding system | `brand/` | JSON token-based theming (default + dark) |
| i18n | `static/i18n/` | UI strings in `en.json` / `de.json` |

---

## Documentation Map

| Document | What it covers |
|----------|---------------|
| `README.md` | Quick start, API reference, project layout |
| `MVP_README.md` | Detailed setup: Docker, KIID retrieval, testing |
| `IMPLEMENTATION_SPEC.md` | Technical spec: algorithm, API contract, JSON schemas |
| `DEVOPS_GUIDE.md` | Docker + GitHub Actions complete guide |
| `DEVOPS_README.md` | DevOps summary: design decisions, security checklist |
| `GITHUB_ACTIONS_GUIDE.md` | CI/CD troubleshooting & best practices reference |
| `GITHUB_ACTIONS_SETUP.md` | GitHub secrets & workflow configuration |
| `BRANDING_GUIDE.md` | Brand pack format, token schema, adding themes |
| `I18N_GUIDE.md` | i18n structure, adding languages, fallback behaviour |
| `CONTRIBUTING.md` | How to contribute, CLA, PR workflow |
| `SECURITY.md` | Vulnerability reporting |

---

## Project Layout

```
FundsPortfolio/
│
├── funds_portfolio/              # Application package
│   ├── app.py                    # Flask entry point + API endpoints
│   ├── data/
│   │   ├── fund_manager.py       # Fund database loader
│   │   └── price_fetcher.py      # yfinance wrapper
│   ├── portfolio/
│   │   ├── decision_engine.py    # Core filter/score/select pipeline
│   │   ├── optimizer.py          # Weight allocation
│   │   ├── calculator.py         # Sharpe Ratio
│   │   ├── validator.py          # Diversification & fee checks
│   │   └── translations/         # Decision message strings (en, de)
│   ├── questionnaire/
│   │   ├── loader.py             # Schema loader + answer validation
│   │   └── translations/         # Questionnaire strings (en, de)
│   └── models/
│       └── portfolio.py          # Portfolio storage model
│
├── templates/                    # HTML frontend
│   ├── index.html
│   └── static/
│
├── static/                       # Frontend assets
│   ├── css/
│   ├── js/
│   └── i18n/                     # UI strings (en.json, de.json)
│
├── brand/                        # Branding themes
│   ├── default/                  # Light theme (brand.json + overrides.css)
│   └── dark/                     # Dark theme
│
├── scripts/                      # Data utilities
│   ├── fetch_kiids.py            # KIID URL retrieval + QS reports
│   ├── import_csv_funds.py       # Import funds from CSV sources
│   └── enrich_funds.py           # Fund data enrichment
│
├── tests/                        # pytest test suite
│   └── test_*.py
│
├── config/
│   └── settings.py               # Flask configuration
│
├── assets/data/                  # Raw data sources (CSV imports)
├── notes/                        # Working files, dev notes
├── portfolios/                   # Saved portfolios (UUID-named JSON, gitignored)
├── reports/                      # KIID QS output (gitignored)
│
├── funds_database.json           # Fund database (~200+ entries)
├── preferences_schema.json       # Questionnaire schema (EN)
├── preferences_schema_DE.json    # Questionnaire schema (DE)
│
├── Dockerfile
├── docker-compose.yml
├── heroku.yml
├── requirements.txt
├── Makefile
└── .github/
    ├── workflows/
    │   ├── ci-cd.yml             # Lint + test + Docker build
    │   ├── test.yml              # PR test runner
    │   └── cla.yml               # CLA check
    └── ISSUE_TEMPLATE/
```

---

## Quick Start

```bash
docker compose up --build
# → http://localhost:5000/
```

Or without Docker:
```bash
pip install -r requirements.txt
PYTHONPATH=. python -m funds_portfolio.app
```

Tests:
```bash
python -m pytest
make ci
```

---

**Governance:** [CONTRIBUTING.md](CONTRIBUTING.md) · [CLA.md](CLA.md) · [LICENSE.md](LICENSE.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md)
