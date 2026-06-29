# Decision-Engine Evaluation Summary

- Config: current (in-tree) DecisionEngine config
- Answer sets evaluated: 1691

## Overall (mean)
- overall: 0.640
- preference: 0.653
- diversification: 0.627

## Preference satisfaction (mean)
- risk_adherence: 1.000
- esg_match: 0.807
- etf_match: 0.879
- region_match: 0.333
- theme_match: 0.258
- theme_coverage: 0.378
- region_match (when active, n=1638): 0.312
- theme_match (when active, n=1665): 0.246

## Diversification (mean)
- provider_div: 0.392 (distinct providers mean: 1.959)
- asset_div: 0.369
- region_div: 0.447
- provider_hhi: 0.625 (lower = more diverse)
- satellite_total: 0.247
- completeness: 0.823

## Behaviour (fractions of answer sets)
- pct_complete (5 funds): 0.629
- pct_empty: 0.037
- pct_hijack: 0.565
- pct_satellite_cap_ok: 0.737
- pct_min_alloc_ok: 0.992
- pct_risk_clean: 1.000

## Boost-hijack diagnostic (mean; reported, not in objective)
- base_gap_top5: -5.462 (selected mean base minus pure-quality top-5 mean base; negative = boosts overrode quality)
- hijack_gap: 16.559 (max non-selected base minus min selected base; >0 = a lower-base fund leapfrogged a higher-base one via boosts)
- boost_dependency: 0.254 (boost share of selected funds' final score)
- thematic_inserts: 0.185
- regional_drops: 0.118
