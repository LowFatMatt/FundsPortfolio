# FundsPortfolio – DevOps & Deployment Guide (MVP)

## 🚀 Deployment Architecture (MVP)

**Stack:**
- **Local Dev**: Docker Compose (flask app + volumes for portfolios/)
- **CI/CD**: GitHub Actions (lint, test, build image)
- **Registry**: Docker Hub or GitHub Container Registry (GHCR)
- **Hosting**: Heroku (Docker) or self-hosted VPS with Docker

**No Authentication:** Portfolios identified by UUID only; no user data stored.

---

## 🐳 Docker Setup

### Dockerfile (MVP)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY funds_portfolio/ ./funds_portfolio/
COPY config/ ./config/
COPY templates/ ./templates/

# Create portfolios directory (will be mounted as volume)
RUN mkdir -p /app/portfolios

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/health')"

# Start gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "funds_portfolio.app:app"]
```

### docker-compose.yml (Local Dev)

```yaml
version: '3.8'

services:
  funds-api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=development
      - LOG_LEVEL=DEBUG
    volumes:
      - ./funds_portfolio:/app/funds_portfolio
      - ./config:/app/config
      - ./portfolios:/app/portfolios
      - ./templates:/app/templates
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  portfolios:
    driver: local
```

**Usage:**
```bash
# Start locally
docker-compose up --build

# Test
curl http://localhost:5000/health

# Access API
curl http://localhost:5000/api/questionnaire

# Stop
docker-compose down
```

---

## 🔄 GitHub Actions Workflow

### .github/workflows/ci-cd.yml

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  DOCKER_BUILDKIT: 1

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov flake8
      
      - name: Lint with flake8
        run: |
          # Stop on errors
          flake8 funds_portfolio --count --select=E9,F63,F7,F82 --show-source --statistics
          # Warn on style issues
          flake8 funds_portfolio --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
      
      - name: Run unit tests
        run: |
          pytest tests/ -v --cov=funds_portfolio --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          fail_ci_if_error: false

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop')
    
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Log in to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix={{branch}}-
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  security-scan:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload Trivy results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v2
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'
```

### .github/workflows/deploy.yml (Optional - Manual Deploy)

```yaml
name: Deploy to Production

on:
  workflow_dispatch:  # Manual trigger
    inputs:
      environment:
        description: 'Deployment environment'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - production

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment }}
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Heroku
        uses: akhileshns/heroku-deploy@v3.12.13
        with:
          heroku_api_key: ${{ secrets.HEROKU_API_KEY }}
          heroku_app_name: ${{ secrets.HEROKU_APP_NAME }}
          heroku_email: ${{ secrets.HEROKU_EMAIL }}
          docker: true
```

---

## 🎯 GitHub Actions Best Practices (DevSecOps)

### Secrets Management

**Set up in GitHub:**
1. go to repo → Settings → Secrets and Variables → Actions
2. Add secrets:
   - `GITHUB_TOKEN`: Auto-provided by GitHub
   - `HEROKU_API_KEY`: Your Heroku auth token
   - `HEROKU_EMAIL`: Heroku account email
   - `HEROKU_APP_NAME`: Your Heroku app name

**Do NOT commit:**
- API keys, tokens, or credentials
- `.env` files
- `config/secrets.json`

### YAML Security Checklist

✅ Use specific action versions (e.g., `@v4` not `@main`)  
✅ Use `secrets.GITHUB_TOKEN` for registry auth (no PATs needed)  
✅ Use `environment` blocks for production deployments  
✅ Enable branch protection rules (require PR reviews)  
✅ Use SARIF for security scan uploads  
✅ Minimize permissions with `permissions:` block  

---

## 🚢 Heroku Deployment (Docker)

### Setup

```bash
# Install Heroku CLI
curl https://cli.heroku.com/install.sh | sh

# Login
heroku login

# Create app
heroku create funds-portfolio-mvp

# Set config vars (environment)
heroku config:set FLASK_ENV=production -a funds-portfolio-mvp

# Set up Docker deployment
heroku apps:info funds-portfolio-mvp
heroku container:push web -a funds-portfolio-mvp
heroku container:release web -a funds-portfolio-mvp

# View logs
heroku logs --tail -a funds-portfolio-mvp
```

### heroku.yml (Alternative: Config-based Deployment)

```yaml
build:
  docker:
    web: Dockerfile

run:
  web: gunicorn --bind 0.0.0.0:$PORT --workers 2 funds_portfolio.app:app

# Release phase for migrations (if needed later)
release:
  image: web
  command: python -c "print('Release phase')"
```

---

## 🔍 Error Handling & QS Process (Semi-Manual)

### KIID Retrieval Error Logging

**Python logging setup:**
```python
import logging
import json
from datetime import datetime

logger = logging.getLogger('kiid_retriever')

def log_kiid_failure(isin, error_reason, fund_name=None):
    """Log failed KIID retrievals for QS review"""
    failure_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "isin": isin,
        "fund_name": fund_name,
        "error": error_reason
    }
    
    # Append to QS log
    with open('logs/kiid_failures.jsonl', 'a') as f:
        f.write(json.dumps(failure_record) + '\n')
    
    logger.warning(f"KIID retrieval failed for {isin}: {error_reason}")

# In fetch_kiids.py script
def fetch_and_validate_batch(isin_list):
    """Batch KIID retrieval with QS flagging"""
    results = {"verified": [], "pending": [], "failed": []}
    
    for isin in isin_list:
        kiid_url = get_kiid_url(isin)
        if kiid_url:
            results["verified"].append({"isin": isin, "kiid_url": kiid_url})
        else:
            results["failed"].append(isin)
            log_kiid_failure(isin, "Search redirect failed")
    
    # Generate QS report
    with open(f'reports/qs_report_{datetime.utcnow().date()}.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    return results
```

### QS Checklist (Manual Review)

After running `fetch_kiids.py` on 20-ISIN sample:

- [ ] Review `kiid_failures.jsonl` for any retrieval issues
- [ ] Manually validate 5 random KIID URLs (can they be downloaded?)
- [ ] Check `kiid_status` field for each fund:
  - `"verified"`: URL confirmed working
  - `"pending"`: Manual review needed
  - `"failed"`: Search didn't find redirect
- [ ] Update `funds_database.json` with status + notes
- [ ] Run unit tests on calculator with sample KIID data

---

## 📊 Monitoring & Observability (Post-MVP)

Once deployed, add:

```yaml
# monitoring.yml (future)
- Prometheus scrape config (Flask `/metrics`)
- ELK stack (logging aggregation)
- Error tracking (Sentry)
- Uptime monitoring (UptimeRobot)
```

For MVP: Use Heroku's built-in logs + manual health checks.

---

## 🔒 Security Hardening (DevSecOps)

### Pre-Production Checklist

- [ ] Run `trivy` locally: `trivy image <image>`
- [ ] Rotate Heroku API key annually
- [ ] Enable GitHub branch protection (require PR reviews)
- [ ] Use environment-specific secrets (staging vs prod)
- [ ] Log all portfolio API calls (audit trail)
- [ ] Add rate limiting to /api/portfolio endpoints (prevent abuse)
- [ ] Use HTTPS only (Heroku enforces by default)
- [ ] Set `Secure` + `HttpOnly` flags on any cookies (if added)

### Dockerfile Security

```dockerfile
# Don't run as root
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Don't use latest; pin Python version
FROM python:3.11-slim

# Use --no-cache-dir to reduce layer size
RUN pip install --no-cache-dir -r requirements.txt
```

---

## 📋 Step-by-Step GitHub Actions Setup

1. **Create workflow directory:**
   ```bash
   mkdir -p .github/workflows
   ```

2. **Add CI/CD workflow file:**
   ```bash
   cat > .github/workflows/ci-cd.yml << 'EOF'
   # [paste workflow YAML above]
   EOF
   ```

3. **Commit and push:**
   ```bash
   git add .github/
   git commit -m "feat: add GitHub Actions CI/CD pipeline"
   git push origin main
   ```

4. **Set secrets in GitHub:**
   - Go to repo → Settings → Secrets and Variables → Actions
   - Add `HEROKU_API_KEY`, `HEROKU_EMAIL`, `HEROKU_APP_NAME`

5. **Monitor first run:**
   - Go to Actions tab
   - Watch CI/CD pipeline execute
   - Review logs for any failures

---

## 🛠 Troubleshooting

### GitHub Actions Fails on Docker Build

**Issue:** `ERROR: failed to solve with frontend dockerfile.v0`

**Fix:**
```yaml
# Use docker/build-push-action v5+ (v4 has issues with 3.11)
- uses: docker/build-push-action@v5
```

### Heroku Deployment Timeout

**Issue:** `Container build timed out after 60m`

**Fix:**
- Reduce layers in Dockerfile
- Use multi-stage build (if needed)
- Optimize `requirements.txt` (remove unnecessary packages)

### Portfolio Files Lost After Restart

**Issue:** Docker-Compose recreates container, portfolio files vanish

**Fix:** The `docker-compose.yml` above uses named volumes; files persist.  
To delete: `docker-compose down -v` (removes volume)

---

## 📝 Checklist for Go-Live

- [ ] GitHub Actions passes all tests
- [ ] Docker image builds & runs locally
- [ ] Heroku app created + secrets configured
- [ ] Manual KIID QS on 20 ISINs completed
- [ ] funds_database.json loaded with status field
- [ ] Health endpoint responds (/health)
- [ ] Sample portfolio API call works (POST /api/portfolio)
- [ ] portfolios/ directory persists across container restarts
- [ ] Logs accessible via `heroku logs --tail`
