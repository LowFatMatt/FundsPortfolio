# Eval baseline — current DecisionEngine config

This directory holds a **frozen, point-in-time snapshot** of the evaluation
harness output for the *current* (in-tree) [`DecisionEngine`](../funds_portfolio/portfolio/decision_engine.py:78)
configuration. It is tracked in git so Phase-2 config sweeps can diff against it.

## Provenance

- **Captured:** 2026-06-29
- **Config:** current in-tree `DecisionEngine` defaults
  - [`BOOST_ELEVATORS`](../funds_portfolio/portfolio/decision_engine.py:55) = `{ETF: 20, ESG: 20, Region: 30, Theme: 45}`
  - constructor: `min_candidates=0` (relaxations off), `top_k=65`,
    `final_fund_count=5`, `max_per_provider=5`, `max_per_category=5`
    (diversification caps effectively off), `min_allocation_percentage=10`
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

Validation: feeding `portfolios/port_20260624_1f0fe187.json`'s `user_answers`
through the live engine reproduces the same 5 funds, and the reported
`region_match` equals the stored exposure (`0.540`).

## Headline numbers (current config)

| Metric | Value |
| --- | --- |
| overall (mean) | 0.640 |
| preference (mean) | 0.653 |
| diversification (mean) | 0.627 |
| pct_hijack | 0.565 |
| base_gap_top5 (mean) | −5.462 |
| region_match (when active) | 0.312 |
| region_coverage (mean) | 0.374 |
| theme_coverage (mean) | 0.378 |
| **pct_theme_full_match (of theme-active)** | **0.228** |
| **pct_region_full_match (of region-active)** | **0.118** |
| pct_complete (5 funds) | 0.629 |

> Read-out: under the current config only **22.8 %** of theme-requesting
> portfolios and **11.8 %** of region-requesting portfolios fully satisfy the
> requested preferences (every requested theme/region represented). The two
> explicit-preference dimensions are where satisfaction collapses — the high
> `preference (mean) 0.653` is carried by risk/ESG/ETF.
