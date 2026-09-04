# Decision-Engine Evaluation Summary

- Config: current (in-tree) DecisionEngine config
- Answer sets evaluated: 1691

## Overall (mean)
- overall: 0.646
- preference: 0.631
- diversification: 0.661

## Preference satisfaction (mean)
- risk_adherence: 1.000
- esg_match: 0.743
- etf_match: 0.858
- region_match: 0.328
- theme_match: 0.238
- theme_coverage: 0.369
- region_coverage: 0.475
- region_match (when active, n=1638): 0.306
- theme_match (when active, n=1665): 0.226

## Diversification (mean)
- provider_div: 0.444 (distinct providers mean: 2.218)
- asset_div: 0.370
- region_div: 0.510
- provider_hhi: 0.568 (lower = more diverse)
- satellite_total: 0.202
- completeness: 0.823

## Behaviour (fractions of answer sets)
- pct_complete (5 funds): 0.629
- pct_empty: 0.037
- pct_hijack: 0.500
- pct_satellite_cap_ok: 0.830
- pct_min_alloc_ok: 0.991
- pct_risk_clean: 1.000
- pct_theme_full_match (of theme-active): 0.213
- pct_region_full_match (of region-active): 0.295

## Boost-hijack diagnostic (mean; reported, not in objective)
- base_gap_top5: -4.468 (selected mean base minus pure-quality top-5 mean base; negative = boosts overrode quality)
- hijack_gap: 14.373 (max non-selected base minus min selected base; >0 = a lower-base fund leapfrogged a higher-base one via boosts)
- boost_dependency: 0.028 (boost share of selected funds' final score)
- pass1_coverage_picks: 1.781
- quota_skips: 0.011
