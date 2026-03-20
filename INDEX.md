# FundsPortfolio MVP – Documentation Index

**Start here!** 👇 Find the right guide for your role.

---

## 🎯 Quick Links by Role

### I'm a **Developer** (Building the App)
1. **Start:** [MVP_README.md](MVP_README.md) – Local setup in 5 minutes
2. **Deep dive:** [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md) – Architecture + API design
3. **Reference:** [preferences_schema.json](preferences_schema.json) – Questionnaire structure

**Phase checklist:**
- [ ] Phase 1: Flask skeleton + JSON loaders
- [ ] Phase 2: KIID retriever + yfinance integration
- [ ] Phase 3: Sharpe Ratio calculator + tests
- [ ] Phase 4: REST API endpoints + HTML forms
- [ ] Phase 5: Ready for DevOps deployment

---

### I'm a **DevOps/Infrastructure Engineer** (You!)
1. **Start:** [DEVOPS_README.md](DEVOPS_README.md) – MVP summary + your responsibilities
2. **Setup guide:** [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md) – Docker + GitHub Actions complete walkthrough
3. **Quick ref:** [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md) – CI/CD troubleshooting + best practices

**Your deliverables:**
- [ ] GitHub repo structure + `.gitignore`
- [ ] GitHub Actions workflows (ci-cd.yml + deploy.yml)
- [ ] Docker image build + GHCR/Docker Hub push
- [ ] Heroku app setup + deployment testing
- [ ] Security hardening (rate limiting, CORS, etc.)
- [ ] Monitoring/logging strategy

---

### I'm a **Financial Analyst** (KIID Validation)
1. **Start:** [MVP_README.md](MVP_README.md) – Section "KIID Retrieval"
2. **Instructions:** Run this command:
   ```bash
   python scripts/fetch_kiids.py --isin-file isins_sample.txt --sample 20 --output reports/
   ```
3. **Review checklist:** `reports/kiid_qc_checklist_*.md` (auto-generated)

**Your workflow:**
- [ ] Receive 20-50 ISINs to validate
- [ ] Run fetch_kiids.py
- [ ] Review "Pending" results manually (Google ISIN, find KIID)
- [ ] Verify KIID URLs work (can download PDF?)
- [ ] Approve/reject for funds_database.json

---

### I'm a **Project Manager**
- **Status:** [DEVOPS_README.md](DEVOPS_README.md) – "What's Been Delivered"
- **Timeline:** [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md) – "Implementation Roadmap"
- **Risks:** See "Troubleshooting" sections in respective guides

---

## 📂 File Structure Explained

```
funds-portfolio/
│
├── 📘 Documentation (Read first!)
│   ├── MVP_README.md              ← Everyone: start here
│   ├── IMPLEMENTATION_SPEC.md      ← Technical deep-dive
│   ├── DEVOPS_GUIDE.md             ← DevOps setup
│   ├── DEVOPS_README.md            ← DevOps summary
│   ├── GITHUB_ACTIONS_GUIDE.md     ← CI/CD troubleshooting
│   └── INDEX.md                    ← This file
│
├── 🐳 Docker & Deployment
│   ├── Dockerfile                  ← Container image definition
│   ├── docker-compose.yml          ← Local dev stack
│   ├── .github/workflows/
│   │   ├── ci-cd.yml               ← GitHub Actions pipeline
│   │   └── deploy.yml              ← Heroku deployment (manual)
│   └── .dockerignore               ← Exclude files from Docker build
│
├── 🐍 Application (Flask Backend)
│   ├── funds_portfolio/
│   │   ├── __init__.py
│   │   ├── app.py                  ← Flask entry point (STUB)
│   │   ├── data/
│   │   │   ├── fund_manager.py     ← Load funds_database.json (STUB)
│   │   │   └── price_fetcher.py    ← yfinance wrapper (STUB)
│   │   ├── portfolio/
│   │   │   ├── calculator.py       ← Sharpe Ratio (STUB)
│   │   │   └── optimizer.py        ← Portfolio allocation (STUB)
│   │   ├── questionnaire/
│   │   │   └── loader.py           ← Load preferences_schema.json (STUB)
│   │   ├── api/
│   │   │   └── routes.py           ← Flask endpoints (STUB)
│   │   └── models/
│   │       └── portfolio.py        ← Data model (STUB)
│   │
│   ├── templates/                  ← HTML/JS (STUB)
│   │   ├── index.html              ← Questionnaire form
│   │   └── static/
│   │
│   ├── tests/                      ← Pytest tests (STUB)
│   │   └── test_*.py
│   │
│   └── config/
│       └── settings.py             ← Flask configuration (STUB)
│
├── 🔧 Scripts & Tools
│   ├── scripts/fetch_kiids.py      ← KIID retrieval tool (READY)
│   └── scripts/                    ← Future: data migration, backups
│
├── 📊 Data Files
│   ├── funds_database.json         ← ~200 funds (SEED DATA)
│   ├── preferences_schema.json     ← Questionnaire (EN) (READY)
│   ├── preferences_schema_DE.json  ← Questionnaire (DE) (READY)
│   ├── isins_sample.txt            ← 20 test ISINs (READY)
│   └── preferences_example_response.json ← Example portfolio (READY)
│
├── 📁 Runtime Directories (Auto-created)
│   ├── portfolios/                 ← User portfolios (JSON files)
│   ├── reports/                    ← QS reports from fetch_kiids.py
│   └── logs/                       ← Application logs
│
└── 🔒 Configuration
    ├── .gitignore                  ← Security: exclude secrets + data
    ├── .env.example                ← (NOT CREATED YET - add before go-live)
    └── requirements.txt            ← Python dependencies (READY)
```

**Note:** (STUB) = File template exists, needs implementation  
**Note:** (READY) = Complete, ready to use  
**Note:** (SEED DATA) = Sample data, replace with real ISINs before production

---

## 📚 Documentation by Topic

### **Getting Started**
- Local development: [MVP_README.md](MVP_README.md#-quick-start-5-minutes)
- Repository setup: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-github-actions-best-practices-devsecops)

### **Architecture & Design**
- System overview: [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#-technical-implementation-details-mvp)
- API endpoints: [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#api-endpoints-mvp---anonymous)
- Data schema: [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#-json-schema-hierarchy-mvp)

### **Docker & Deployment**
- Local Docker: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-docker-setup)
- GitHub Actions: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-github-actions-workflow)
- Heroku deployment: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-heroku-deployment-docker)
- CI/CD troubleshooting: [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md#-troubleshooting-workflows)

### **KIID Retrieval & QS**
- Batch retrieval: [MVP_README.md](MVP_README.md#-kiid-retrieval-semi-manual-qs)
- Script usage: [scripts/fetch_kiids.py](scripts/fetch_kiids.py) (see `--help`)
- Error handling: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-error-handling---qs-process-semi-manual)

### **Security**
- Secrets management: [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md#-secrets-management)
- Docker security: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-security-hardening-devsecops)
- Pre-production checklist: [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-security-hardening-devsecops)

---

## 🎯 Phase-by-Phase Deliverables

| Phase | Duration | Deliverables | Owner |
|-------|----------|-------------|-------|
| **1: Foundation** | Weeks 1-2 | Flask skeleton, JSON loaders, Docker ✓ | Dev |
| **2: Data Layer** | Week 3 | KIID retriever, yfinance integration | Dev + Analyst |
| **3: Calculations** | Weeks 4-5 | Sharpe Ratio, portfolio optimizer, tests | Dev |
| **4: API & UI** | Week 6 | REST endpoints, HTML form, database | Dev |
| **5: DevOps** | Week 7 | GitHub Actions, Docker image, Heroku deploy | You |

**Current status:** Pre-Phase 1 (all specifications ready)

---

## 🔍 How to Use This Index

### "I'm stuck on Docker"
→ [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md#-docker-setup) or [MVP_README.md](MVP_README.md#-docker-development)

### "GitHub Actions workflow failed"
→ [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md#-troubleshooting-workflows)

### "How do I set up the project?"
→ [MVP_README.md](MVP_README.md#-quick-start-5-minutes)

### "What is the API contract?"
→ [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#api-endpoints-mvp---anonymous)

### "What are my DevOps responsibilities?"
→ [DEVOPS_README.md](DEVOPS_README.md#-your-next-steps-devsecops-lead)

### "How do I retrieve KIID documents?"
→ [scripts/fetch_kiids.py](scripts/fetch_kiids.py) + [MVP_README.md](MVP_README.md#-kiid-retrieval-semi-manual-qs)

---

## 📋 Pre-Development Checklist

Before starting Phase 1, ensure:

- [ ] All team members have GitHub access
- [ ] Python 3.13 installed locally (for testing)
- [ ] Docker & Docker Compose installed
- [ ] All documentation reviewed (this index + specific guides)
- [ ] 200-ISIN list sourced
- [ ] Heroku account ready (for Phase 5)
- [ ] KIID analyst available (for Phase 2)
- [ ] DevOps engineer (you!) committed 20-25 hours

---

## 🚀 Getting Started (TL;DR)

**1. Read these in order:**
```
MVP_README.md (10 min)
  → IMPLEMENTATION_SPEC.md (20 min)
    → DEVOPS_GUIDE.md (30 min)
```

**2. Test locally:**
```bash
docker-compose up --build
curl http://localhost:5000/health
```

**3. Test KIID retrieval:**
```bash
python scripts/fetch_kiids.py --isin-file isins_sample.txt --sample 5
```

**4. Confirm architecture:**
- JSON storage ✓
- Anonymous portfolios ✓
- Docker local dev ✓
- GitHub Actions ready ✓

**5. Create GitHub repo & start Phase 1!**

---

## 📞 Quick Reference

**For questions about:**
- **Flask app structure** → [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#backend-python)
- **Docker setup** → [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md)
- **API endpoints** → [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md#api-endpoints-mvp---anonymous)
- **GitHub Actions** → [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md)
- **KIID retrieval** → [scripts/fetch_kiids.py](scripts/fetch_kiids.py)
- **Data schema** → [funds_database.json](funds_database.json) + [preferences_schema.json](preferences_schema.json)

---

**Last Updated:** 4. März 2026  
**MVP Status:** Ready for Phase 1 development  
**Doc Version:** 1.0
