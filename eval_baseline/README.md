# Eval baseline — frozen DecisionEngine snapshot (2026-09-04, v3.2)

This directory holds a **frozen, point-in-time snapshot** of the evaluation
harness output for the in-tree [`DecisionEngine`](../funds_portfolio/portfolio/decision_engine.py:87)
configuration **as of the capture date below**. It is tracked in git so
config sweeps can diff against it — notably the upcoming core-satellite /
allocation rework branch.

> **Regenerate before committing this README update** (provenance below
> describes the intended v3.2 capture):
>
> ```bash
> PYTHONPATH=. python scripts/eval_decision_engine.py --answer-grid-cap 1691 --out eval_baseline
> rm -f eval_baseline/per_answer_metrics.csv   # *.csv is gitignored; keep dir pristine
> ```
>
> Then replace the *Headline numbers* placeholder table from the fresh
> `summary.md`.

## Provenance

- **Captured:** 2026-09-04
- **Config:** in-tree `DecisionEngine` defaults at tag time
  - [`BOOST_ELEVATORS`](../funds_portfolio/portfolio/decision_engine.py:58) = `{ETF: 6, ESG: 6, Region: 0, Theme: 0}` (v3.2: all boosts tie-breaker-level — preferences are honored structurally via pass-1 coverage, hard filters and dialog feasibility gating; see [`FUND_SELECTION_LOGIC_SPEC_V3.md`](../FUND_SELECTION_LOGIC_SPEC_V3.md) Step 6)
  - **Allocation:** inverse-volatility tier ranking — cores sorted by inverse
    volatility before tier assignment (Core 1 = most stable; regression
    `test_core_tiers_assigned_by_inverse_volatility_not_selection_order`,
    fixed 2026-09-03 after `port_20260903_f2245f4e`)
  - constructor: `min_candidates=0` (relaxations off), `top_k=65`,
    `final_fund_count=5`, `max_per_provider=5`, `max_per_category=5`
    (provider/category caps effectively off), `max_per_specific_theme=2`,
    `max_per_specific_region=2`, `min_allocation_percentage=10`
  - **Selection:** two-pass, coverage-first (Step 7 in
    [`FUND_SELECTION_LOGIC_SPEC_V3.md`](../FUND_SELECTION_LOGIC_SPEC_V3.md)) —
    pass 1 covers preferred regions/themes from the full ranking, pass 2 fills
    from the top; per-kind quotas are enforced as selection skips, never as
    post-selection drops.
- **Fund universe:** [`funds_database.json`](../funds_database.json) — 64 funds
- **Answer grid:** full 57,888-combination space, stride-capped to **1691**
  answers (matches the reference sample size from
  `notes/API-Test-Fonds-Portfolio-Service.py`)

## Files

- `summary.json` — machine-readable aggregate (means/medians/min/max per metric)
- `summary.md` — human-readable summary

## Count invariant

Across the full answer grid, every portfolio with fewer than 5 funds is
**filter-limited** (fewer than 5 eligible funds after ESG/ETF/risk-band
filters — universe thinness); **zero** are selection-limited. The two-pass
selection never returns fewer funds than the eligible universe allows.

## Headline numbers (v3.2 capture — PENDING REGENERATION)

| Metric | Value |
| --- | --- |
| overall (mean) | _refresh from new summary.md_ |
| preference (mean) | _refresh from new summary.md_ |
| diversification (mean) | _refresh from new summary.md_ |
| num_funds (mean) | _refresh from new summary.md_ |
| base_gap_top5 (mean) | _refresh from new summary.md_ |
| region_match (when active) | _refresh from new summary.md_ |
| region_coverage (mean) | _refresh from new summary.md_ |
| theme_coverage (mean) | _refresh from new summary.md_ |
| pass1_coverage_picks (mean) | _refresh from new summary.md_ |
| quota_skips (mean) | _refresh from new summary.md_ |

_Previous capture (2026-08-17, boosts 45/45/70/70) for comparison:
overall 0.652 · preference 0.665 · diversification 0.639 · num_funds 4.114
(627/1691 filter-limited) · base_gap_top5 −7.494 · region_match 0.400 ·
region_coverage 0.475 · theme_coverage 0.374 · pass1_coverage_picks 1.675 ·
quota_skips 0.630._
