# FundsPortfolio — Documentation Index

Hub for all project documentation. The product's current feature set lives in
[README.md](README.md); this file maps **what documentation exists and where**.

---

## What's Built

| Component | File(s) | Notes |
|-----------|---------|-------|
| Flask app & API | `funds_portfolio/app.py` | All endpoints (core + charts/breakdowns/health) |
| Decision engine | `funds_portfolio/portfolio/decision_engine.py` | Filter → score → select → allocate (two-pass coverage-first; Core-Satellite + inverse-vol weighting; integer allocation output) |
| Shared risk bands | `funds_portfolio/portfolio/risk_bands.py` | Single source of truth for DEFENSIVE/BALANCED/OPPORTUNITY bands (Slide 8); engine backstop and dialog advisor both delegate here |
| Shared eligibility | `funds_portfolio/portfolio/eligibility.py` | Single source of truth for ESG (SFDR Art. 8/9) and ETF-only filter semantics; engine and advisor both delegate here |
| Sharpe calculator | `funds_portfolio/portfolio/calculator.py` | Risk-adjusted return scoring |
| Validator | `funds_portfolio/portfolio/validator.py` | Diversification, fee, count checks (max_fee default 1.50%) |
| Preference reporting | `funds_portfolio/portfolio/preference_match.py` | Single source of truth for preference-satisfaction scoring (engine output, trace, eval, GUI) |
| Portfolio aggregator | `funds_portfolio/portfolio/aggregator.py` | Weighted NAV + breakdown rollups |
| Data-provider abstraction | `funds_portfolio/data/providers/` | `DataProvider` ABC + `JsonFileProvider` + `get_provider()` factory honouring `CUSTOMER` env var |
| Fund manager (facade) | `funds_portfolio/data/fund_manager.py` | Read-only delegate over the configured provider |
| Stress-period config | `funds_portfolio/config/stress_periods.py` | Reads `data/stress_periods.json` |
| Price fetcher | `funds_portfolio/data/price_fetcher.py` | yfinance wrapper (legacy enrichment) |
| Questionnaire loader | `funds_portfolio/questionnaire/loader.py` | Loads & validates user answers; decorates theme AND region options with per-(profile × esg8_9 × etf_only) feasible fund counts |
| Feasibility advisor v2 | `funds_portfolio/dialog/feasibility.py` | Answer-space shaping: themes+regions gated by risk band ∧ ESG-only ∧ ETF-only filters (L2 availability) plus a shared selection budget DEF 1 / BAL 2 / OPP 3 (L1); pure functions, soft warnings for direct API calls |
| Eval harness | `funds_portfolio/eval/` + `scripts/eval_decision_engine.py` | Answer grid, config sweeps (boost elevators), metrics, reporting |
| Portfolio model | `funds_portfolio/models/portfolio.py` | UUID persistence to disk |
| Web UI | `templates/index.html` + `static/` | M3-styled SPA, 4 result tabs (Summary / Preferences / Performance / Volatility) |
| Chart helpers | `static/js/charts.js` | Lazy-loads Chart.js v4 + annotation + date-fns adapter from CDN |
| Branding system | `brand/` | JSON token-based theming (default + dark); selected via `BRAND` env var |
| i18n | `static/i18n/` | UI strings in `en.json` / `de.json` (incl. `stress.*`, period, vol & gating labels) |
| Scraper (offline) | `scripts/sync_factsheetslive.py` | Pulls per-ISIN data into `data/funds/{ISIN}.json` |
| Customer catalog tools | `scripts/build_customer_catalog.py`, `scripts/select_customer.py` | Build a customer-specific catalog and activate it |
| UI modes & flows | `MODES.md`, `flows/`, `static/js/app.js` | Quick-Mode (`?mode=quick`) + Flow-Mode wizard (`?mode=flow&flowVariant=A\|B`); shared result component; declarative flow configs |

---

## Documentation Map

### Product & Architecture

| Document | What it covers |
|----------|---------------|
| `README.md` | **Start here.** Quick start, current feature list, API reference, data sources |
| `FUND_SELECTION_LOGIC_SPEC_V3.md` | Fund selection logic v3.1: filter pipeline, scoring formula + boost rationale, two-pass coverage-first selection, Core-Satellite allocation, edge cases (authoritative for the engine) |
| `FUND_SELECTION_LOGIC_SPEC_V3_DE.md` | German translation of the v3 spec (specification-faithful; English version is authoritative) |
| `MODES.md` | UI modes (Quick/Flow), the single-API contract, shared result component, declarative flow definitions (`showIf`, gating metadata, A/B variants) |
| `docs/user-journey/` | User-journey distillation from PDF/PPT sources vs. prototype: state diagrams, coverage matrix (screen ↔ PDF-ID ↔ PPT-slide ↔ flow-step ↔ status), gaps & product decisions, per-screen specs, `data-testid` contract |
| `BRANDING_GUIDE.md` | Brand pack format, token schema, adding themes |
| `I18N_GUIDE.md` | i18n structure, adding languages, fallback behaviour |

### Operations & Governance

| Document | What it covers |
|----------|---------------|
| `DEVOPS_GUIDE.md` | Docker + deployment guide |
| `DEVOPS_README.md` | DevOps summary: design decisions, security checklist |
| `GITHUB_ACTIONS_GUIDE.md` | CI/CD troubleshooting & best practices reference |
| `GITHUB_ACTIONS_SETUP.md` | GitHub secrets & workflow configuration |
| `CONTRIBUTING.md` · `CLA.md` · `CODE_OF_CONDUCT.md` · `SECURITY.md` · `LICENSE.md` | Contribution process & project governance |

### Historical & Evaluation

| Document | Status |
|----------|--------|
| `MVP_README.md` | Historical MVP-era guide (bannered in-file) |
| `IMPLEMENTATION_SPEC.md` | Original technical spec — high-level structure still informative; engine details **superseded** by the V3 spec (bannered in-file) |
| `Questions_de_de.md` · `Investment_Preferences_DE.md` · `Investment_Preferences_EN.md` | Original questionnaire source material (historical, bannered in-file) |
| `eval_baseline/` | Frozen 2026-08-17 evaluation snapshot (README documents provenance in place); regenerate via `scripts/eval_decision_engine.py` |
| `eval_proof_on/` · `eval_proof_off/` | Point-in-time sweep artifacts (dated; regenerable) |

**Working plans:** dated design documents live in the local, **gitignored**
`plans/` directory — intentionally not part of the repo. Each carries its own
status line (planned / implemented / superseded).

---

## Project Layout

```
FundsPortfolio/
│
├── funds_portfolio/              # Application package
│   ├── app.py                    # Flask entry point + API endpoints
│   ├── dialog/                   # Dialog-layer answer-space shaping
│   │   └── feasibility.py        # Feasibility advisor (pure functions)
│   ├── portfolio/
│   │   ├── decision_engine.py    # Filter/score/select/allocate pipeline
│   │   ├── risk_bands.py         # Shared risk-band definitions (Slide 8)
│   │   ├── eligibility.py        # Shared ESG/ETF filter semantics
│   │   ├── preference_match.py   # Preference-satisfaction reporting
│   │   ├── calculator.py         # Sharpe Ratio
│   │   ├── validator.py          # Diversification & fee checks
│   │   ├── aggregator.py         # Weighted NAV + breakdown rollups
│   │   └── translations/         # Decision message strings (en, de)
│   ├── eval/                     # Evaluation harness (grid, sweeps, metrics)
│   ├── data/
│   │   ├── providers/            # DataProvider ABC + JSON provider + factory
│   │   ├── fund_manager.py       # Fund database facade
│   │   └── price_fetcher.py      # yfinance wrapper
│   ├── questionnaire/
│   │   ├── loader.py             # Schema loader + validation + feasibility decoration
│   │   └── translations/         # Questionnaire strings (en, de)
│   ├── models/
│   │   └── portfolio.py          # Portfolio storage model
│   └── scrapers/                 # Scraper base + finanzen.py
│
├── templates/                    # HTML frontend (index.html)
├── static/                       # Frontend assets (css / js / i18n)
│
├── flows/                        # Declarative flow definitions (variantA/B.json)
│
├── docs/
│   └── user-journey/             # Journey distillation (README / screens / testids)
│
├── brand/                        # Branding themes (default + dark)
│
├── scripts/                      # Data & evaluation utilities
│   ├── sync_factsheetslive.py    # Scrape per-ISIN data → data/funds/
│   ├── build_customer_catalog.py # Build a customer-specific catalog
│   ├── select_customer.py        # Activate a customer profile
│   ├── eval_decision_engine.py   # Run the eval harness / sweeps
│   └── tune_decision_engine.py   # Boost tuning sweeps
│
├── tests/                        # pytest test suite (test_*.py)
│
├── eval_baseline/                # Frozen eval snapshot (tracked, provenance in README)
├── eval_proof_on/  eval_proof_off/  # Point-in-time sweep artifacts (tracked)
│
├── data/
│   ├── customers/{id}/           # Per-customer fund catalogs (general, provinzial_nord)
│   ├── funds/{ISIN}.json         # Per-ISIN time-series (scraped)
│   ├── benchmarks.json           # App-level reference benchmarks
│   └── stress_periods.json       # Performance-chart overlay config
├── data_sources.yaml             # DataProvider config
├── config/
│   └── settings.py               # Flask configuration
│
├── assets/data/                  # Raw data sources (CSV imports)
├── notes/                        # Working files, dev notes (gitignored)
├── portfolios/                   # Saved portfolios (gitignored)
├── reports/                      # KIID QS output (gitignored)
├── plans/                        # Dated design docs (gitignored, local only)
│
├── funds_database.json           # Active fund database (managed by select_customer.py)
├── preferences_schema.json       # Questionnaire schema + preference_gating (EN)
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

