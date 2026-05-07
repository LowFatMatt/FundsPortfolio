# FundsPortfolio – Implementation Specification & Next Steps

## 📋 Further Specification Details

### 1. Question-to-Portfolio Mapping

The questionnaire responses map to portfolio calculations as follows:

| Question | Impact | Calculation |
|----------|--------|-------------|
| **Investment Goal** | Portfolio naming + time horizon validation | Retirement goals → Conservative; Wealth building → Moderate-Aggressive |
| **Duration** | Risk tolerance adjustment | Longer duration → More equity exposure allowed |
| **Monthly Savings** | Portfolio size constraints | Determines minimum fund allocation amounts |
| **Experience** | Educational content + risk ceiling | No experience → Conservative options only |
| **Knowledge Level** | UI complexity + fund explanation depth | Beginners → Simplified fund descriptions |
| **Risk Approach** | Equity/Bond allocation % | Conservative (100% bonds), Moderate-Low (60/40), Moderate (70/30), Aggressive (80/20) |
| **Loss Tolerance** | Portfolio volatility ceiling | Low tolerance → Max 15% annual volatility; High → 25%+ allowed |

### 2. Sharpe Ratio Calculation

```
Sharpe Ratio = (Return - Risk-Free Rate) / Standard Deviation

Process:
1. Extract historical performance from KIID for each fund
2. Calculate expected annual return (historical + trend analysis)
3. Calculate standard deviation (volatility)
4. Rank funds by Sharpe Ratio
5. Filter top 100 funds
6. Use Modern Portfolio Theory (Efficient Frontier) to optimize
```

### 3. Portfolio Optimization Algorithm

For each user profile:
1. **Filter funds** by risk level + asset class matching
2. **Diversify** across regions + asset classes
3. **Optimize weights** using Sharpe Ratio ranking
4. **Validate** against:
   - Volatility ceiling
   - Fee constraints (avg < 0.5% annually)
   - Minimum fund count (5-10 for diversification)

### 4. Data Sources Required (MVP)

**KIID Retrieval Strategy:**
```python
# Pseudo-code for KIID URL discovery
def get_kiid_url(isin):
    # 1. Try iShares UK search (most common)
    search_url = f"https://www.ishares.com/uk/individual/en/search?searchTerm={isin}"
    resp = requests.get(search_url, allow_redirects=False)
    if resp.status_code in (301, 302):
        return resp.headers['Location']  # KIID document URL
    
    # 2. Fallback: Try DE, FR sites
    # 3. Log failure for manual review
    return None
```

**Data Sources:**
- **ISINs (200 list)**: Mix of iShares, Vanguard, SPDR ETFs + mutual funds
- **KIID Documents**: Retrieved via iShares/fund provider search redirects
- **Historical Prices**: yfinance (daily close for 5 years)
- **Risk-Free Rate**: ECB main refinancing rate OR static 2% (MVP simplification)

---

## 🛠️ Technical Implementation Details (MVP)

### Backend (Python)

**Core Modules:**
```
funds_portfolio/
├── app.py                       # Flask entry point + all API endpoints
├── data/
│   ├── fund_manager.py          # Load/cache funds_database.json
│   └── price_fetcher.py         # yfinance integration
├── portfolio/
│   ├── decision_engine.py       # Filter → score → select → allocate pipeline
│   ├── calculator.py            # Sharpe Ratio calculations
│   ├── validator.py             # Risk/fee/diversification checks
│   ├── optimizer.py             # Portfolio weight allocation
│   └── translations/            # Decision message strings (en.json, de.json)
├── questionnaire/
│   ├── loader.py                # Load + validate preferences_schema.json
│   └── translations/            # Questionnaire strings (en.json, de.json)
└── models/
    └── portfolio.py             # Portfolio storage + UUID persistence

scripts/
├── fetch_kiids.py               # Batch KIID URL retrieval + QS reporting
├── import_csv_funds.py          # Import funds from CSV sources
└── enrich_funds.py              # Fund data enrichment utilities
```

**Key Libraries (MVP):**
- `Flask`: Lightweight REST API
- `pandas`, `numpy`: Data manipulation & calculations
- `scipy.optimize`: Portfolio optimization (constrained)
- `yfinance`: Historical fund/stock data
- `requests`: KIID URL retrieval
- `gunicorn`: WSGI server (for Docker)
- `pytest`: Unit testing

### Frontend (Interactive)

**User Flow:**
1. Load questionnaire from `preferences_schema.json`
2. Collect answers → POST to backend
3. Backend calculates portfolio → Returns portfolio_id + recommendations
4. Display recommended funds with:
   - Fund name, ISIN, annual fee
   - Risk level, Sharpe Ratio
   - Allocation % in the portfolio
   - Link to fund KIID document

**API Endpoints:**
```
GET  /health
   → { "status": "ok" }

GET  /api/questionnaire
   → Returns preferences_schema.json (questions + dynamic region/theme options)

POST /api/portfolio
   Body: { "user_answers": { "investment_goal": "...", "risk_approach": "...", ... } }
   → 201: { "portfolio_id", "risk_profile", "recommendations",
             "portfolio_metrics", "explanations", "decision_trace" }
   → 400: { "error", "details" } on validation failure

GET  /api/portfolio/{portfolio_id}
   → Retrieves saved portfolio from portfolios/{id}.json

GET  /api/funds
   → Returns full funds_database.json (for inspection/debugging)
```

---

## 📝 JSON Schema Hierarchy (MVP)

```
preferences_schema.json
├── questionnaire (static configuration)
│   ├── sections (7 question groups)
│   │   ├── options (possible answers; region/theme populated dynamically from DB)
│   │   └── metadata (required, type, etc.)
│   └── version

funds_database.json (~200+ funds)
├── funds_database (array)
│   ├── isin, name, provider, ticker
│   ├── asset_class, region, theme, categories
│   ├── risk_level (1-5), srri (1-7), yearly_fee
│   ├── is_etf, esg_label, esg_article_8, esg_article_9
│   ├── sharpe_ratio
│   ├── kiid_url, kiid_status ("verified"|"pending"|"failed")
│   └── notes
└── metadata (last_updated, total_funds)

portfolios/{portfolio_id}.json
├── portfolio_id            # "port_YYYYMMDD_UUID8"
├── created_at              # ISO 8601
├── user_answers            # answers from questionnaire
├── risk_profile            # "DEFENSIVE" | "BALANCED" | "OPPORTUNITY"
├── recommendations[]       # selected funds with allocation_percent + rationale
├── portfolio_metrics
│   ├── weighted_fee        # weighted average TER
│   ├── srri_proxy          # weighted average SRRI
│   └── exposures           # by asset class, region, theme
├── explanations
│   ├── summary             # human-readable summary string
│   └── per_fund{}          # per-ISIN explanation strings
└── decision_trace
    ├── filters[]           # each filter: name, before count, after count
    ├── relaxations[]       # any risk-band relaxations applied
    └── used_fallback_risk  # bool
```

