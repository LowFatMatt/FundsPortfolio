# Eval baseline — frozen DecisionEngine snapshot (2026-08-17)

This directory holds a **frozen, point-in-time snapshot** of the evaluation
harness output for the in-tree [`DecisionEngine`](../funds_portfolio/portfolio/decision_engine.py:87)
configuration **as of the capture date below**. It is tracked in git so
config sweeps can diff against it.

> **Note:** the engine has moved on since capture (v3.1 boost re-tuning,
> 2026-08-31 — see [`FUND_SELECTION_LOGIC_SPEC_V3.md`](../FUND_SELECTION_LOGIC_SPEC_V3.md)
> Step 6). Diff against this baseline with that in mind, or regenerate it.

## Provenance

- **Captured:** 2026-08-17
- **Config:** current in-tree `DecisionEngine` defaults
  - [`BOOST_ELEVATORS`](../funds_portfolio/portfolio/decision_engine.py:58) = `{ETF: 45, ESG: 45, Region: 70, Theme: 70}`
  - constructor: `min_candidates=0` (relaxations off), `top_k=65`,
    `final_fund_count=5`, `max_per_provider=5`, `max_per_category=5`
    (provider/category caps effectively off), `max_per_specific_theme=2`,
    `max_per_specific_region=2`, `min_allocation_percentage=10`
  - **Selection:** two-pass, coverage-first (see Step 7 in
    [`FUND_SELECTION_LOGIC_SPEC_V3.md`](../FUND_SELECTION_LOGIC_SPEC_V3.md)) —
    pass 1 covers preferred regions/themes from the full ranking, pass 2 fills
    from the top; per-kind quotas are enforced as selection skips, never as
    post-selection drops. `thematic_inserts`/`regional_drops` KPIs were replaced
    by `pass1_coverage_picks`/`quota_skips`.
- **Fund universe:** [`funds_database.json`](../funds_database.json) — 64 funds
- **Answer grid:** full 57,888-combination space, stride-capped to **1691**
  answers (matches the reference sample size from
  `notes/API-Test-Fonds-Portfolio-Service.py`)

## Files

- `summary.json` — machine-readable aggregate (means/medians/min/max per metric)
- `summary.md` — human-readable summary

## How to regenerate

Per-run output goes to a gitignored `eval_results*/` dir; only this baseline is
tracked. To refresh the baseline intentionally:

```bash
PYTHONPATH=. python scripts/eval_decision_engine.py --answer-grid-cap 1691 --out eval_baseline
rm -f eval_baseline/per_answer_metrics.csv   # *.csv is gitignored; keep dir pristine
```

Validation: feeding `portfolios/port_20260709_e763ed0b.json`'s `user_answers`
through the live engine now reproduces **5 funds / 7-of-7 preference
satisfaction** (the frozen portfolio file itself predates the two-pass rework
and shows the old 3-fund / 6-of-7 outcome).

## Count invariant (2026-08-17 rework)

Across the full 1691-answer grid, every portfolio with fewer than 5 funds is
**filter-limited** (fewer than 5 eligible funds after ESG/ETF/risk-band
filters — universe thinness); **zero** are selection-limited. The two-pass
selection never returns fewer funds than the eligible universe allows.

## Headline numbers (current config)

| Metric | Value |
| --- | --- |
| overall (mean) | 0.652 |
| preference (mean) | 0.665 |
| diversification (mean) | 0.639 |
| num_funds (mean) | 4.114 (627/1691 filter-limited below 5) |
| base_gap_top5 (mean) | −7.494 |
| region_match (when active) | 0.400 |
| region_coverage (mean) | 0.475 |
| theme_coverage (mean) | 0.374 |
| pass1_coverage_picks (mean) | 1.675 |
| quota_skips (mean) | 0.630 |
