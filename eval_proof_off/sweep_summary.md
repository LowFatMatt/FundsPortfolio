# Decision-Engine Boost Sweep

> **Point-in-time artifact.** Sweep run predates the v3.1 boost re-tuning
> (2026-08-31): large Region/Theme boosts were still meaningful then. Under
> the two-pass coverage-first selection these dimensions are guaranteed by
> pass 1 — see FUND_SELECTION_LOGIC_SPEC_V3.md Step 6 for the current
> rationale. Regenerate via `scripts/tune_decision_engine.py` before citing.

- Answer sets per config: 2000
- Configs evaluated: 2402
- Objective: 75% preference + 25% diversification
- Pareto-optimal configs: 66
- Regime: no_thematic_guarantee (thematic_guarantee / regional_cap engine flags applied during the sweep)

## Recommended config (rank 1)
- boosts: ETF=45 ESG=45 Region=60 Theme=60
- composite: 0.645  (overall 0.639, pref 0.650, div 0.629)
- pct_hijack: 0.563  base_gap_top5: -6.240
- region_match (active): 0.282  theme_coverage: 0.286
- pct_theme_full_match: 0.116  pct_region_full_match: 0.301

## Diff vs current live config (positive overall = better)
- overall: +0.005
- pref_score: +0.013
- div_score: -0.004
- pct_hijack: +0.000 (negative = less hijacking)
- base_gap_top5: -1.610 (positive = less quality loss)
- pct_theme_full_match: -0.009 (positive = more themes fully met)
- pct_region_full_match: +0.046 (positive = more regions fully met)

## Top 10 configs
| rank | ETF | ESG | Reg | Thm | overall | pref | div | pct_hijack | base_gap_top5 | d_overall | d_pct_hijack | pareto |
|------|-----|-----|-----|-----|---------|------|-----|------------|---------------|-----------|--------------|--------|
| 1 | 45 | 45 | 60 | 60 | 0.639 | 0.650 | 0.629 | 0.563 | -6.240 | +0.005 | +0.000 | yes |
| 2 | 30 | 45 | 60 | 60 | 0.639 | 0.650 | 0.628 | 0.566 | -6.466 | +0.004 | +0.003 | yes |
| 3 | 60 | 45 | 60 | 60 | 0.639 | 0.649 | 0.630 | 0.562 | -6.162 | +0.005 | -0.000 | yes |
| 4 | 30 | 60 | 60 | 60 | 0.638 | 0.650 | 0.627 | 0.566 | -6.492 | +0.004 | +0.003 |  |
| 5 | 45 | 60 | 60 | 60 | 0.638 | 0.649 | 0.627 | 0.563 | -6.273 | +0.003 | +0.000 |  |
| 6 | 20 | 45 | 60 | 60 | 0.638 | 0.649 | 0.627 | 0.566 | -6.464 | +0.003 | +0.003 |  |
| 7 | 10 | 45 | 60 | 60 | 0.637 | 0.649 | 0.626 | 0.560 | -6.702 | +0.003 | -0.002 |  |
| 8 | 60 | 60 | 60 | 60 | 0.638 | 0.648 | 0.627 | 0.562 | -6.149 | +0.003 | -0.000 |  |
| 9 | 45 | 30 | 60 | 60 | 0.638 | 0.647 | 0.629 | 0.563 | -5.848 | +0.004 | +0.000 |  |
| 10 | 20 | 60 | 60 | 60 | 0.637 | 0.649 | 0.625 | 0.566 | -6.521 | +0.002 | +0.003 |  |

Live baseline rank: 241 (overall 0.635, pct_hijack 0.562)
