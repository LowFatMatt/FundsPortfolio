# FundsPortfolio — DevOps Summary

Quick reference for deployment, infrastructure, and CI/CD. For the full guide see [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md).

---

## Key Design Decisions

| Decision | Approach | Reasoning |
|----------|----------|-----------|
| **Fund Database** | JSON file | Easy to manage; no SQL migration needed until ~500+ funds |
| **KIID Retrieval** | Semi-manual QS process | Automated iShares search + human review for edge cases |
| **Portfolio Storage** | JSON files in `portfolios/` | No database, no auth complexity; UUID-based anonymity |
| **Frontend** | HTML/JS (no framework) | Fast delivery; React can be added later if needed |
| **Deployment** | Docker on Heroku | Straightforward scaling; portable to any Docker host |
| **Authentication** | None (anonymous) | No PII stored; portfolios accessed by UUID only |
| **CI/CD** | GitHub Actions | Free tier; Trivy security scanning; Docker build on push |

---

## CI/CD Overview

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci-cd.yml` | push / PR | ruff lint + pytest + Docker build + Trivy scan + GHCR push |
| `test.yml` | PR | pytest only (fast feedback) |
| `cla.yml` | PR | CLA signature check |

Secrets required: `HEROKU_API_KEY`, `HEROKU_EMAIL`, `HEROKU_APP_NAME`
See [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) for setup steps.

---

## Docker Quick Reference

```bash
# Local dev
docker compose up --build
docker compose logs -f funds-api
docker compose down

# Production image test
docker build -t funds-portfolio:latest .
docker run -e FLASK_ENV=production -p 5000:5000 funds-portfolio:latest

# Heroku deploy
heroku container:push web -a funds-portfolio-mvp
heroku container:release web -a funds-portfolio-mvp
```

---

## Security Checklist

### Code
- [ ] No API keys/tokens in Git (use GitHub secrets / environment variables)
- [ ] Trivy scans passing in GitHub Actions
- [ ] Docker image runs as non-root user
- [ ] Python dependencies pinned (no `>=` wildcards)

### Data
- [ ] No user PII stored (portfolios are UUID-only)
- [ ] `.gitignore` excludes `portfolios/`, `logs/`, `.env`
- [ ] `funds_database.json` versioned in Git (it is the source of truth)
- [ ] HTTPS enforced (Heroku default)

### Deployment
- [ ] Branch protection enabled (require PR + CI pass)
- [ ] GitHub secrets configured (not hardcoded anywhere)
- [ ] Health check responds at `GET /health`
- [ ] Rate limiting in place before public exposure

---

## KIID Retrieval Workflow

```bash
# Run on a batch of ISINs
python scripts/fetch_kiids.py --isin-file isins_sample.txt --sample 20 --output reports/

# Output:
#   reports/kiid_retrieval_*.json       — full results (verified/pending/failed)
#   reports/kiid_qc_checklist_*.md      — manual review checklist
```

Manual review: for each "Pending" ISIN, find the KIID URL manually and verify the PDF downloads. Update `funds_database.json` with `"kiid_status": "verified"`.

---

**See also:** [DEVOPS_GUIDE.md](DEVOPS_GUIDE.md) · [GITHUB_ACTIONS_GUIDE.md](GITHUB_ACTIONS_GUIDE.md) · [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md)
