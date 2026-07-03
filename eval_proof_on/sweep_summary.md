# Decision-Engine Boost Sweep

- Answer sets per config: 2000
- Configs evaluated: 2402
- Objective: 75% preference + 25% diversification
- Pareto-optimal configs: 84
- Regime: default (thematic_guarantee / regional_cap engine flags applied during the sweep)

## Recommended config (rank 1)
- boosts: ETF=60 ESG=45 Region=60 Theme=5
- composite: 0.650  (overall 0.647, pref 0.654, div 0.639)
- pct_hijack: 0.562  base_gap_top5: -6.152
- region_match (active): 0.272  theme_coverage: 0.374
- pct_theme_full_match: 0.240  pct_region_full_match: 0.300

## Diff vs current live config (positive overall = better)
- overall: +0.011
- pref_score: +0.011
- div_score: +0.012
- pct_hijack: -0.003 (negative = less hijacking)
- base_gap_top5: -0.570 (positive = less quality loss)
- pct_theme_full_match: +0.006 (positive = more themes fully met)
- pct_region_full_match: +0.067 (positive = more regions fully met)

## Top 10 configs
| rank | ETF | ESG | Reg | Thm | overall | pref | div | pct_hijack | base_gap_top5 | d_overall | d_pct_hijack | pareto |
|------|-----|-----|-----|-----|---------|------|-----|------------|---------------|-----------|--------------|--------|
| 1 | 60 | 45 | 60 | 5 | 0.647 | 0.654 | 0.639 | 0.562 | -6.152 | +0.011 | -0.003 | yes |
| 2 | 60 | 45 | 60 | 10 | 0.646 | 0.654 | 0.639 | 0.562 | -6.165 | +0.011 | -0.003 | yes |
| 3 | 45 | 45 | 60 | 5 | 0.646 | 0.654 | 0.639 | 0.562 | -6.162 | +0.011 | -0.003 |  |
| 4 | 45 | 45 | 60 | 10 | 0.646 | 0.654 | 0.639 | 0.562 | -6.184 | +0.011 | -0.003 |  |
| 5 | 60 | 45 | 60 | 0 | 0.647 | 0.653 | 0.640 | 0.557 | -6.099 | +0.011 | -0.008 | yes |
| 6 | 45 | 45 | 60 | 0 | 0.647 | 0.653 | 0.640 | 0.557 | -6.122 | +0.011 | -0.008 |  |
| 7 | 60 | 45 | 60 | 20 | 0.645 | 0.654 | 0.636 | 0.562 | -6.341 | +0.010 | -0.002 | yes |
| 8 | 45 | 45 | 60 | 20 | 0.645 | 0.654 | 0.635 | 0.562 | -6.368 | +0.010 | -0.002 |  |
| 9 | 45 | 60 | 60 | 10 | 0.646 | 0.654 | 0.637 | 0.562 | -6.213 | +0.010 | -0.003 | yes |
| 10 | 60 | 60 | 60 | 10 | 0.645 | 0.654 | 0.637 | 0.562 | -6.147 | +0.010 | -0.003 | yes |

Live baseline rank: 910 (overall 0.635, pct_hijack 0.565)
