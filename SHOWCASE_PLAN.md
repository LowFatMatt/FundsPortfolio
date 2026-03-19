# Next‑Level Showcase Plan (2–3 Weeks, Consumer Self‑Serve)

## Summary
Ship a user‑visible “decision filtering” showcase by upgrading the recommendation engine to honor richer preferences (ESG, ETF, region, theme), add transparent explainability, and tighten validation. Defer ops work like DB migration and caching until after the showcase proves value.

## Key Changes (By Stage With Deliverables and Acceptance Criteria)

### Week 1 — Decision Filtering Core
- Deliverable — Implement a decision engine pipeline (filter → score → select → allocate → validate) based on the OptimizerPseudoCode structure, using existing fund fields (`srri`, `yearly_fee`, `region`, `theme`, `esg_label`, `is_etf`, `risk_level`) and fallback metrics when price history is missing.
- Deliverable — Map questionnaire answers to a 3‑tier risk profile (DEFENSIVE/BALANCED/OPPORTUNITY) and enforce required answers instead of the current “accept‑all” fallback.
- Deliverable — Add an “audit/trace” object that records filters applied, relaxations used, and the reasoning for inclusion/exclusion.
- Acceptance — ETF‑only preference returns 100% ETF funds; ESG‑required excludes funds below the ESG threshold; preferred regions/themes influence selection weights; missing required answers return a 400 with clear errors; the pipeline produces a stable top‑N set for identical inputs.

### Week 2 — Explainability & UI Showcase
- Deliverable — Preferred regions/themes are generated from the fund database and refreshed when the database changes.
- Deliverable — Extend API response to include portfolio metrics (risk profile, estimated volatility proxy, weighted fee), plus per‑fund explanation strings.
- Deliverable — Update the UI to display “why these funds” and show how preferences affected the result (ESG, ETF, region, theme).
- Deliverable — Add a “decision summary” panel that highlights the key filters and constraints applied.
- Acceptance — A user can see a clear, human‑readable rationale for each fund; the decision summary references their selected preferences; the recommendation output still sums to 100% allocations and passes all validation checks.

### Week 3 — Stabilization & Documentation (Buffer Week)
- Deliverable — Add tests for each preference dimension (ESG required, ETF‑only, region/theme preference) and for explainability payload shape.
- Deliverable — Update documentation to match actual endpoints and payloads, including the new explainability fields.
- Acceptance — Tests cover the new decision filters and fail on regressions; docs accurately reflect request/response shapes.

### Week 4 — Contributor‑Ready Workflow (Parallel Track)
- Deliverable — Implement GitHub Actions CI as described in `GITHUB_ACTIONS_SETUP.md` and `GITHUB_ACTIONS_GUIDE.md` for lint + tests on PRs.
- Deliverable — Keep deployment local only (Docker Compose) for now; no Heroku deployment steps.
- Deliverable — Add contributor docs and templates (CONTRIBUTING, PR template, issue template) and a short “how to run CI locally” section.
- Acceptance — A new contributor can run `docker compose up --build` and `python -m pytest` successfully, and CI status checks appear on PRs.
- Note — Provide light coaching for GitHub Actions workflow steps when requested; assume strong DevSecOps background but limited GH Actions hands‑on.

## Public API Changes
- `POST /api/portfolio` response adds `risk_profile`, `portfolio_metrics`, `explanations`, and `decision_trace`.
- Validation errors return consistent 4xx error objects with field‑level messages.
- Request schema stays compatible but enforces required fields more strictly.

## Test Plan
- Unit tests for filtering (ESG/ETF/region/theme) and scoring weighting.
- Integration tests for “preference‑driven” outputs (ETF‑only, ESG required, region preference).
- API tests to assert new response fields and error handling.

## Assumptions
- Showcase scope uses existing fund fields and minimal new data enrichment.
- No DB migration or caching in this phase; JSON storage remains.
- 2–3 weeks is acceptable for a focused, demonstrable upgrade.
