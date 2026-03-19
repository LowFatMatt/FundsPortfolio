# GitHub Actions Quick Reference (DevSecOps)

**For:** Quick troubleshooting + hands-on learning of CI/CD pipelines

---

## 🔄 GitHub Actions Basics

### What Triggers Workflows?

```yaml
on:
  push:
    branches: [main, develop]     # On commit to main/develop
  pull_request:
    branches: [main]               # On PR to main
  schedule:
    - cron: '0 2 * * *'           # Daily at 2 AM UTC
  workflow_dispatch:               # Manual trigger (Actions tab)
```

### Workflow Structure

```
Push to main
  ↓
.github/workflows/ci-cd.yml triggers
  ↓
jobs:
  ├─ test (runs on ubuntu-latest)
  │  ├─ Checkout code
  │  ├─ Setup Python
  │  ├─ Run pytest
  │  └─ Upload coverage
  │
  ├─ build (needs: test)
  │  ├─ Login to Docker registry
  │  ├─ Build Docker image
  │  └─ Push to GHCR
  │
  └─ security-scan (parallel)
     └─ Run Trivy scan
```

---

## ⚡ Common Commands

### View Workflow Status

```bash
# From CLI (GitHub CLI installed)
gh workflow list
gh run list
gh run view <run-id>
gh run logs <run-id>

# Web UI
# Go to repo → Actions tab → Click workflow
```

### Trigger Manual Workflow

```bash
# Workflow must have: on: workflow_dispatch:
gh workflow run ci-cd.yml --ref main

# Web UI: Actions → Select workflow → Run workflow button
```

### View Secrets

```bash
# List (not values, for security)
gh secret list

# Create
gh secret set MY_SECRET --body "secret-value"

# Delete
gh secret delete MY_SECRET
```

---

## 🐛 Troubleshooting Workflows

### Workflow Not Triggering

**Issue:** Push to main but workflow didn't run  
**Checklist:**
- [ ] Workflow file is in `.github/workflows/`
- [ ] File ends with `.yml` or `.yaml`
- [ ] Workflow has `on:` section with your trigger event
- [ ] Branch name matches (e.g., `main` not `master`)

**Fix:**
```bash
git log --oneline | head -5  # Confirm commit was pushed
gh run list --limit 10        # Check if run exists
```

### Test Locally (Before Pushing)

```bash
# Install act (local GitHub Actions runner)
brew install act  # macOS
# or: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | bash

# Run workflow locally
act push -j test  # Run just the 'test' job
act -l             # List all jobs

# Run with secrets
act --secret MY_SECRET=value
```

### Docker Build Fails in CI

**Issue:** `ERROR: failed to solve with frontend dockerfile.v0`

**Common causes:**
1. Dockerfile has syntax errors
2. Large dependencies (yfinance, scipy) timeout
3. Docker buildx cache issue

**Fix:**
```yaml
# In ci-cd.yml, use build-push-action v5+
- uses: docker/build-push-action@v5
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### Secrets Not Loading

**Issue:** `Error: env variable is empty`

**Checklist:**
- [ ] Secret exists: `gh secret list`
- [ ] Syntax correct in YAML: `${{ secrets.MY_SECRET }}`
- [ ] Workflow file was pushed (not just editied locally)
- [ ] Workflow has `permissions` to read secrets (if in org)

**Fix:**
```bash
# Re-add secret
gh secret set MY_SECRET --body "$(cat ~/.secret)"

# Wait 2-3 mins before re-running
```

### Matrix Builds Failing Partially

**Scenario:** Tests run for Python 3.10 but fail for 3.11  
**Strategy:** 
- Don't use `fail-fast: true` for debugging
- Check logs by matrix value: `strategy: { matrix: { python: [3.10, 3.11] } }`
- Each combination gets separate log tab in UI

---

## 🔒 Secrets Management

### Secure Practices

✅ **DO:**
- Use GitHub secrets for API keys
- Rotate secrets annually
- Use separate secrets for staging vs production
- Limit secret scope (environment-specific)

❌ **DON'T:**
- Commit `.env` files
- Log secrets (GitHub masks `***` automatically)
- Use personal access tokens as secrets (use `GITHUB_TOKEN`)
- Share secret values in PRs/discussions

### Setting Secrets

```bash
# Organization secrets (all repos can use)
gh secret set --org MY_ORG MY_SECRET --body "value"

# Repository secrets (only this repo)
gh secret set MY_SECRET --body "value"

# Environment secrets (only for specific env)
gh secret set --env production MY_SECRET --body "value"
```

### Using in Workflow

```yaml
jobs:
  deploy:
    environment: production  # Uses secrets from 'production' env
    steps:
      - run: echo ${{ secrets.HEROKU_API_KEY }}  # Masked in logs as ***
      - run: heroku auth:token  # Never do this!
```

---

## 📊 Monitoring Workflows

### Dashboard (Web UI)

```
repo → Actions tab
│
├─ All workflows (list of files)
├─ Recent runs (green✓ or red✗)
└─ Run details
   ├─ Jobs (test, build, etc.)
   ├─ Logs (step-by-step output)
   ├─ Artifacts (uploaded files)
   └─ Summary (duration, status)
```

### Status Badge (Add to README)

```markdown
[![CI/CD](https://github.com/youruser/funds-portfolio/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/youruser/funds-portfolio/actions)
```

### Notifications

- Default: Email when workflow fails
- Advanced: Slack/Discord webhooks (add action)
  ```yaml
  - name: Slack notification
    uses: slackapi/slack-github-action@v1
    with:
      webhook-url: ${{ secrets.SLACK_WEBHOOK }}
  ```

---


---

## 🧭 Coaching Checklist (First Runs)

Use this quick list when you want a guided, low-stress first run.

### First Local Run (No GitHub Yet)
- [ ] Run `python -m pytest` locally (baseline signal).
- [ ] If tests fail, fix locally before pushing.
- [ ] Optional: run `act push -j test` if you want to simulate Actions locally.

### First GitHub Actions Run
- [ ] Push a small change to a branch (not `main`).
- [ ] Open a PR and watch the Actions tab for the CI run.
- [ ] Click into the run and expand the `test` job logs.
- [ ] Confirm the workflow uses the correct Python version and runs pytest.

### If It Fails
- [ ] Read the first error in the log (usually the root cause).
- [ ] Re-run only after a local fix.
- [ ] If in doubt, paste the failing log section and we’ll triage together.

##  🚀 Deploying with GitHub Actions
### Status

Local Docker only for now. Skip this section until we decide to deploy.



### Deploy to Heroku (Manual Trigger)

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment environment'
        type: choice
        options:
          - staging
          - production

jobs:
  deploy:
    environment: ${{ github.event.inputs.environment }}
    steps:
      - uses: akhileshns/heroku-deploy@v3
        with:
          heroku_api_key: ${{ secrets.HEROKU_API_KEY }}
          heroku_email: ${{ secrets.HEROKU_EMAIL }}
          heroku_app_name: ${{ secrets.HEROKU_APP_NAME }}
```

### Auto-Deploy on Main Branch

```yaml
on:
  push:
    branches: [main]

jobs:
  deploy:
    if: github.event_name == 'push'
    steps:
      - run: heroku container:push web -a my-app
      - run: heroku container:release web -a my-app
```

---

## 📈 Advanced Patterns

### Conditional Steps

```yaml
- name: Deploy
  if: github.ref == 'refs/heads/main' && success()
  run: ./deploy.sh
```

### Artifacts (Upload/Download Files)

```yaml
# Upload test coverage
- uses: actions/upload-artifact@v3
  with:
    name: coverage-report
    path: htmlcov/

# Download from previous job
- uses: actions/download-artifact@v3
  with:
    name: coverage-report
```

### Matrix Builds (Test Multiple Versions)

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.10', '3.11']
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
```

### Timeouts (Prevent Hanging)

```yaml
jobs:
  build:
    timeout-minutes: 10
    steps:
      - run: long-running-command
        timeout-minutes: 5
```

---

## 📋 Your MVP Workflow Checklist

### Before Committing `.github/workflows/ci-cd.yml`

- [ ] `on: push` triggers on `main` and `develop` branches
- [ ] `test` job runs `pytest` + linting
- [ ] `build` job depends on `test` passing
- [ ] Docker credentials use GitHub secrets
- [ ] Image tags include branch name + SHA
- [ ] Health check scripts exist (`/health` endpoint)
- [ ] Trivy security scan runs automatically

### First Deploy

1. **Do a test run locally:**
   ```bash
   act push -j test  # Test job only
   ```

2. **Push to develop branch:**
   ```bash
   git push origin develop
   ```

3. **Watch Actions tab** (should run test job)

4. **Review logs** for any failures

5. **Merge to main** once develop tests pass

6. **Monitor build job** (Docker push to GHCR)

---

## 🆘 Getting Help

### GitHub Documentation
- [Official Docs](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Security Best Practices](https://docs.github.com/en/actions/security-guides)

### Community Resources
- [Awesome GitHub Actions](https://github.com/sdras/awesome-actions)
- Stack Overflow: tag `github-actions`
- GitHub Community Forum: `discussions`

### Debugging
```bash
# Enable debug logging (set secret)
gh secret set ACTIONS_STEP_DEBUG --body "true"

# Re-run with debug enabled
# Actions tab → Run details → Re-run with debug logs
```

---

## ✅ Learning Path (Your DevSecOps Growth)

**Week 1:** Set up basic CI (lint + test)  
**Week 2:** Add Docker build + push  
**Week 3:** Implement security scanning (Trivy)  
**Week 4:** Manual deployment (Heroku)  
**Week 5+:** Auto-deployment + monitoring  

---

**Last Updated:** 4. März 2026  
**Audience:** DevSecOps / Infrastructure Engineers  
