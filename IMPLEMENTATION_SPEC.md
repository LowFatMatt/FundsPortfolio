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
├── data/
│   ├── fund_manager.py      # Load/save funds_database.json
│   ├── kiid_retriever.py    # iShares search + redirect logic
│   └── price_fetcher.py     # yfinance integration
├── portfolio/
│   ├── calculator.py        # Sharpe Ratio + optimization
│   ├── validator.py         # Risk/fee/diversification checks
│   └── optimizer.py         # Portfolio weighting algorithm
├── questionnaire/
│   ├── loader.py           # Load preferences_schema.json
│   └── validator.py        # Validate user answers
├── api/
│   ├── routes.py           # Flask endpoints
│   └── serializer.py       # JSON response formatting
├── models/
│   ├── fund.py             # Fund data model
│   └── portfolio.py        # Portfolio storage model
└── scripts/
    └── fetch_kiids.py      # Batch KIID URL retrieval + QS reporting
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

**API Endpoints (MVP - Anonymous):**
```
GET /api/questionnaire
   → Returns preferences_schema.json

POST /api/portfolio
   Body: { "user_answers": {...} }
   → Creates new portfolio, returns { "portfolio_id", "recommendations", "metadata" }

GET /api/portfolio/{portfolio_id}
   → Retrieves stored portfolio JSON from disk

PUT /api/portfolio/{portfolio_id}
   Body: { "user_answers": {...} }
   → Updates answers, recalculates, saves portfolio

GET /api/funds
   → Returns funds_database.json (for inspection)

GET /health
   → Returns { "status": "ok" }
```

---

## 📝 JSON Schema Hierarchy (MVP)

```
preferences_schema.json
├── questionnaire (static configuration)
│   ├── sections (7 question groups)
│   │   ├── options (possible answers)
│   │   └── metadata (required, type, etc.)
│   └── version control

funds_database.json (~200 funds, MVP)
├── funds_database (array of fund objects)
│   ├── ISIN, name, provider
│   ├── kiid_url (retrieved via iShares search redirect)
│   ├── kiid_status ("verified", "pending", "failed")
│   ├── asset class, region, categories
│   ├── risk_level (1-5), yearly_fee
│   └── notes (QS validation remarks)
└── metadata (last_updated, total_funds, retrieval_date)

portfolios/ (local JSON storage)
├── {portfolio_id}.json (one file per portfolio)
│   ├── portfolio_id (UUID)
│   ├── created_at, updated_at
│   ├── user_answers (from preferences_schema questions)
│   ├── calculated_metrics
│   │   ├── risk_profile (1-4)
│   │   ├── suitable_fund_categories
│   │   └── diversification_needs
│   └── recommended_funds (array with allocations %)
└── .gitignore (ignore portfolio files)
```

---

## 🎯 Implementation Roadmap (Phased)

### **Phase 1: Foundation (Weeks 1-2)**
- [ ] Set up Git repo structure
- [ ] Create API skeleton (Flask/FastAPI)
- [ ] Implement JSON loaders for questionnaire + funds
- [ ] Build basic user answer validation

### **Phase 2: Data Layer (Weeks 3-4)**
- [ ] Fund manager (CRUD for funds_database.json)
- [ ] KIID retriever script (iShares search → 302 redirect → PDF URL)
- [ ] yfinance data fetcher
- [ ] Semi-manual QS validation (test 20 ISINs, verify KIID URLs)

### **Phase 3: Calculation Engine (Weeks 5-6)**
- [ ] Sharpe Ratio calculator
- [ ] Modern Portfolio Theory optimizer
- [ ] Risk/fee validator
- [ ] Unit tests for calculations

### **Phase 4: API & Frontend (Weeks 7-8)**
- [ ] REST endpoints for questionnaire
- [ ] Portfolio creation/retrieval endpoints
- [ ] HTML/JS questionnaire renderer
- [ ] Portfolio results display

### **Phase 5: Polish & Deployment (Week 9)**
- [ ] Integration testing
- [ ] Performance optimization
- [ ] Documentation + README updates
- [ ] Deploy to hosting platform

---

## 🔧 Required Skills

| Skill | Level | Duration |
|-------|-------|----------|
| Python (pandas, numpy, scipy) | Advanced | 2-3 weeks |
| REST API Design | Intermediate | 1 week |
| Financial Calculations (Sharpe, Optimization) | Intermediate | 2 weeks |
| JavaScript/HTML/CSS | Intermediate | 1 week |
| JSON/Database schema design | Intermediate | 1 week |
| Git + testing (pytest) | Basic | Throughout |

**Recommended Team (MVP):**
- 1 Backend Developer (Python/API/Docker) – primary
- You: DevSecOps/Infrastructure (GitHub Actions, Docker, deployment strategy)
- Ad-hoc: Financial analyst for 20-ISIN QS validation

---

## ✅ Checklist Before Starting

- [ ] Assemble list of ~200 ISINs (iShares, Vanguard, SPDR mix)
- [ ] Test KIID retrieval script on 20 sample ISINs
- [ ] MVP: Keep funds_database.json; no SQL migration yet
- [ ] Set up GitHub Actions: linting, testing on push
- [ ] Error handling: Log failed ISINs; flag KIID retrieval failures for manual review
- [ ] Authentication: Anonymous (no sign-up); portfolios stored by UUID only
- [ ] Deployment: Docker image + docker-compose.yml for local testing
