# FundsPortfolio — Documentation Index

**Status:** Phase 2.5 complete — questionnaire-driven recommender + Performance/Volatility charts + customer-specific fund universes. Next: Phase 3 (multi-customer architecture).

---

## What's Built

| Component | File(s) | Notes |
|-----------|---------|-------|
| Flask app & API | `funds_portfolio/app.py` | All endpoints (Phase 1 core + Phase 2 charts/breakdowns/health) |
| Decision engine | `funds_portfolio/portfolio/decision_engine.py` | Filter → score → select → allocate |
| Portfolio optimizer | `funds_portfolio/portfolio/optimizer.py` | Weight allocation by risk profile |
| Sharpe calculator | `funds_portfolio/portfolio/calculator.py` | Risk-adjusted return scoring |
| Validator | `funds_portfolio/portfolio/validator.py` | Diversification, fee, count checks (max_fee default 1.50%) |
| Portfolio aggregator | `funds_portfolio/portfolio/aggregator.py` | Phase 2: weighted NAV + breakdown rollups |
| Data-provider abstraction | `funds_portfolio/data/providers/` | Phase 2: `DataProvider` ABC + `JsonFileProvider` + `get_provider()` factory honouring `CUSTOMER` env var |
| Fund manager (facade) | `funds_portfolio/data/fund_manager.py` | Read-only delegate over the configured provider |
| Stress-period config | `funds_portfolio/config/stress_periods.py` | Reads `data/stress_periods.json` |
| Price fetcher | `funds_portfolio/data/price_fetcher.py` | yfinance wrapper (legacy enrichment) |
| Questionnaire loader | `funds_portfolio/questionnaire/loader.py` | Loads & validates user answers |
| Portfolio model | `funds_portfolio/models/portfolio.py` | UUID persistence to disk |
| Web UI | `templates/index.html` + `static/` | M3-styled SPA, 4 result tabs (Summary / Preferences / Performance / Volatility) |
| Chart helpers | `static/js/charts.js` | Lazy-loads Chart.js v4 + annotation + date-fns adapter from CDN |
| Branding system | `brand/` | JSON token-based theming (default + dark); selected via `BRAND` env var |
| i18n | `static/i18n/` | UI strings in `en.json` / `de.json` (incl. `stress.*`, period & vol labels) |
| Scraper (offline) | `scripts/sync_factsheetslive.py` | Pulls per-ISIN data into `data/funds/{ISIN}.json` |
| Customer catalog tools | `scripts/build_customer_catalog.py`, `scripts/select_customer.py` | Phase 2.5: build a customer-specific catalog and activate it |

---

## Documentation Map

| Document | What it covers |
|----------|---------------|
| `README.md` | **Start here.** Quick start, current feature list, API reference, project layout |
| `MVP_README.md` | Historical MVP-era guide (see banner at top of file) — Docker, KIID retrieval, original scope |
| `IMPLEMENTATION_SPEC.md` | Technical spec: algorithm, API contract, JSON schemas — high-level still accurate, engine details superseded by V2 spec below |
| `FUND_SELECTION_LOGIC_SPEC_V2.md` | Fund selection logic v2: filter pipeline, scoring formula, Core-Satellite allocation, edge cases (authoritative for the engine) |
| `DEVOPS_GUIDE.md` | Docker + GitHub Actions complete guide |
| `DEVOPS_README.md` | DevOps summary: design decisions, security checklist |
| `GITHUB_ACTIONS_GUIDE.md` | CI/CD troubleshooting & best practices reference |
| `GITHUB_ACTIONS_SETUP.md` | GitHub secrets & workflow configuration |
| `BRANDING_GUIDE.md` | Brand pack format, token schema, adding themes |
| `I18N_GUIDE.md` | i18n structure, adding languages, fallback behaviour |
| `CONTRIBUTING.md` | How to contribute, CLA, PR workflow |
| `SECURITY.md` | Vulnerability reporting |

**Plans (off-tree, in `~/.claude/plans/`)**

| File | Status |
|---|---|
| `ok-then-on-spicy-parrot.md` | Phase 2.5 — Customer-specific catalog (Provinzial Nord). **Done.** |
| `phase-3-multi-customer.md` | Phase 3 — Multi-customer architecture (profile.yaml, master registry, ingestion pipeline). **Next.** |

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
│   ├── fetch_kiids.py            # KIID URL retrieval + QS reports (legacy)
│   ├── import_csv_funds.py       # Import funds from CSV sources (legacy)
│   ├── enrich_funds.py           # Fund data enrichment (legacy)
│   ├── sync_factsheetslive.py    # Phase 2: scrape per-ISIN data → data/funds/
│   ├── build_customer_catalog.py # Phase 2.5: build a customer-specific catalog
│   ├── select_customer.py        # Phase 2.5: activate a customer profile
│   └── _german_labels.py         # Shared taxonomy helpers
│
├── data/                         # Phase 2 data layout
│   ├── customers/{id}/           # Per-customer fund catalogs (general, provinzial_nord)
│   │   └── funds_database.json
│   ├── funds/{ISIN}.json         # Per-ISIN time-series (scraped, ~all 127 covered)
│   ├── benchmarks.json           # App-level reference benchmarks
│   └── stress_periods.json       # Performance-chart overlay config
├── data_sources.yaml             # DataProvider config
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
