# Decision-Engine Evaluation Summary

- Config: current (in-tree) DecisionEngine config
- Answer sets evaluated: 1691

## Overall (mean)
- overall: 0.652
- preference: 0.665
- diversification: 0.639

## Preference satisfaction (mean)
- risk_adherence: 1.000
- esg_match: 0.809
- etf_match: 0.882
- region_match: 0.400
- theme_match: 0.243
- theme_coverage: 0.374
- region_coverage: 0.475
- region_match (when active, n=1638): 0.380
- theme_match (when active, n=1665): 0.231

## Diversification (mean)
- provider_div: 0.415 (distinct providers mean: 2.076)
- asset_div: 0.368
- region_div: 0.486
- provider_hhi: 0.609 (lower = more diverse)
- satellite_total: 0.237
- completeness: 0.823

## Behaviour (fractions of answer sets)
- pct_complete (5 funds): 0.629
- pct_empty: 0.037
- pct_hijack: 0.564
- pct_satellite_cap_ok: 0.742
- pct_min_alloc_ok: 0.998
- pct_risk_clean: 1.000
- pct_theme_full_match (of theme-active): 0.223
- pct_region_full_match (of region-active): 0.294

## Boost-hijack diagnostic (mean; reported, not in objective)
- base_gap_top5: -7.494 (selected mean base minus pure-quality top-5 mean base; negative = boosts overrode quality)
- hijack_gap: 21.017 (max non-selected base minus min selected base; >0 = a lower-base fund leapfrogged a higher-base one via boosts)
- boost_dependency: 0.377 (boost share of selected funds' final score)
- pass1_coverage_picks: 1.675
- quota_skips: 0.630
