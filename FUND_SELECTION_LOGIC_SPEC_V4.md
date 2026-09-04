# Fund Selection Logic — Specification v4
**Source:** Provinzial "Fondsauswahllogik – Fondskompass" (March 2026); v3 evolved 2026-09-04  
**Implementation:** [`funds_portfolio/portfolio/decision_engine.py`](funds_portfolio/portfolio/decision_engine.py)  
**Predecessor:** v3 at [`FUND_SELECTION_LOGIC_SPEC_V3.md`](FUND_SELECTION_LOGIC_SPEC_V3.md)

> **v4 headline changes:**
> 1. **Satellite classification** now distinguishes funds selected *only because of* pass 1 preferences from those that would have ranked top-5 anyway (Step 8)
> 2. **Allocation logic** switched from inverse-volatility + tier bounds to **proportional elevated-score weighting** with satellite/core bands (Steps 9–11)

---

## Overview

The fund selection logic operates in three sequential phases, each fully recorded in a machine-readable decision trace:

| Phase | Goal | Output |
|-------|------|--------|
| **1 — Filter** | Exclude ineligible funds (data quality, ESG, ETF, risk band) | Reduced fund universe |
| **2 — Scoring** | Score remaining funds: quantitative base + preference boosts | Single ranked list (the ranking) |
| **3 — Portfolio Construction** | Two-pass selection of 5 funds, then Core-Satellite weighting | 5-fund portfolio with allocations + full decision log |

---

## Phase 1 — Filter

Funds pass sequential hard filters before being admitted to scoring. The trace records each filter with before/after counts.

### Step 0 — Required Fields Filter

Exclude funds lacking any of: `isin`, `name`, `yearly_fee`, `sharpe_ratio`, `max_drawdown`, `srri` (or `risk_level`), `volatility`. Regulatory distribution status (approval for Germany, not in wind-down) is guaranteed upstream by database curation.

> Fallbacks in later stages tolerate single missing metrics (SRRI proxies, Step 5), but the required-fields gate keeps the universe data-complete.

### Step 1 — ESG Filter

ESG is a single three-case preference (`esg_preference`); Article 8 and 9 count together as "sustainable" (derived from `esg_label`):

- **`ART_8_9_ONLY`** — hard filter: keep only `SFDR_ARTICLE_8` / `SFDR_ARTICLE_9`.
- **`PREFER_ESG`** — no exclusion here; sustainable funds get a scoring boost (Step 6).
- **`NONE`** — ESG ignored entirely (legacy answer values are normalised to these three).

### Step 2 — ETF Preference Filter

- **`etf_only`** — hard filter: keep only `is_etf` funds. If fewer than 5 ETFs remain after all filters, the ETF-only fallback (Step 7, end) fills the remaining positions with active funds.
- **`prefer_etf`** — no exclusion; ETFs get a scoring boost (Step 6).
- **`no_preference`** — no action.

### Step 3 — Risk Band Filter

Map `risk_approach` (conservative / moderate / aggressive) to a three-tier profile and apply the bands of the authoritative slide (Step 8 of the source deck):

| Parameter | DEFENSIVE | BALANCED | OPPORTUNITY *(= Growth-Oriented)* |
|-----------|-----------|----------|-----------------|
| SRRI (or `risk_level`) | 1–3 | 2–5 | 4–7 |
| Annual volatility | ≤ 8 % | 5–15 % | ≥ 10 % (no upper bound) |
| Max Drawdown | < 15 % | < 30 % | < 50 % |

Bands intentionally overlap to avoid abrupt exclusion at boundaries.

### Step 4 — Regional & Thematic Preferences *(soft — no filter)*

Region and theme preferences never exclude funds. They act through (a) the coverage pass (Step 7, pass 1) — which guarantees each preferred value is covered — and (b) the satellite classification (Step 8) — which distinguishes coverage-driven selections from quality-driven ones.

> Region and theme scoring boosts are **disabled** (set to 0 since v3.2) because preferences are honored structurally through pass 1 coverage guarantees, not through ranking manipulation.

### Relaxations and Warnings *(gated by `min_candidates`)*

- **Risk-band relaxation:** if fewer than `min_candidates` funds remain, widen the band by ±1 SRRI and ±5 % volatility. Currently **disabled** (`min_candidates = 0`), so an over-restrictive universe falls through honestly instead of silently widening.
- **Final-fund floor:** with `min_candidates > 0`, if the risk band leaves fewer than 5 funds but the pre-risk pool has enough, revert to the pre-risk pool (also disabled by default).
- **Universe warning:** if 0 < remaining < 3, the trace carries a warning that the portfolio may contain funds at the edge of the suitability range.

---

## Phase 2 — Scoring

### Step 5 — Base Quality Score (0–100)

Each eligible fund receives a composite score from three min-max normalised metrics (normalisation spans the eligible universe of the current session, scale 0–10):

```
base = (Sharpe_norm × 5.0) + (MDD_norm × 3.0) + (TER_norm × 2.0)
```

| Component | Metric | Weight | Direction |
|-----------|--------|--------|-----------|
| Risk-adjusted return | Sharpe Ratio | 50 % | higher is better |
| Drawdown protection | Maximum Drawdown | 30 % | lower is better (inverted) |
| Cost efficiency | TER (`yearly_fee`) | 20 % | lower is better (inverted) |

Proxies when a metric is missing at scoring time: MDD ← `SRRI_MDD_PROXY[srri]`, volatility ← `SRRI_VOL_PROXY[srri]` (used in allocation).

**Ranking sort order** (deterministic): final score ↓, then Sharpe ↓, then fee ↑, then ISIN ↓.

### Step 6 — Preference Boosts (on top of base)

**Rationale (v3.2 re-tuning, unchanged in v4):** preferences are honored *structurally*, not by ranking force. Preferred regions/themes are guaranteed by the coverage pass (Step 7, pass 1); hard preference filters (`ART_8_9_ONLY`, `etf_only`) are enforced in Step 1; and the dialog's feasibility gating ([`funds_portfolio/dialog/feasibility.py`](funds_portfolio/dialog/feasibility.py)) shapes the answer space so only honorable combinations are offered in the first place. Boosts therefore no longer need to steer selection and are reduced to nominal tie-breakers: **ETF/ESG +6** (reorder near-equal candidates only), **Region/Theme 0** (fully disabled — boosting covered dimensions would only distort the quality-driven ranking of pass 2).

| Boost | Condition | Value (default `BOOST_ELEVATORS`) |
|-------|-----------|------|
| ETF | `prefer_etf` and fund `is_etf` | **+6** |
| ESG | `PREFER_ESG` and `esg_label` ∈ {Art. 8, 9} | **+6** |
| Region | `fund.region` exactly in `preferred_regions` | **0** (disabled) |
| Theme | `fund.theme` in `preferred_themes` (placeholder `NONE` disables) | **0** (disabled) |

`ART_8_9_ONLY` is a hard filter only (no boost). A fund can accumulate multiple boosts (e.g. ETF + ESG).

---

## Phase 3 — Portfolio Construction

### Step 7 — Selection: Two-Pass, Coverage-First, Purely Additive

Selection operates on the single ranked list and only ever **adds** funds. No fund is dropped, protected, or swapped after being selected — the portfolio size can only grow toward `final_fund_count` (5). The count is safe by construction.

**Pass 1 — coverage (preferences first).** Walk the *full* ranking in quality order and select a fund only if it matches at least one **still-unsatisfied** preferred region or theme. Stop when every preferred value is covered, no candidate exists anywhere in the ranking, or the portfolio is full.

- The guarantee toggles gate pass 1 per dimension: `thematic_guarantee` (themes), `regional_guarantee` (regions). Defaults: on.
- One pick can satisfy several values at once (fund carries a preferred region *and* theme); the collateral match is recorded as `also_satisfies`.
- Quota-compliant candidates are preferred (sweep A). If a preferred value remains unsatisfied and the only carrying fund would breach its quota, **coverage beats quota**: the best such fund is selected and the breach is logged explicitly (sweep B).

**Pass 2 — fill (best remaining).** Restart at the top of the `top_k` pool — excluding funds already selected in pass 1 (the effective pool is smaller than `top_k`) — and fill the remaining slots with the best funds regardless of preference match, subject to the constraints below.

**Constraints — enforced as skips during selection, never as drops after it:**

| Constraint | Parameter (default) | Scope |
|------------|---------------------|-------|
| Max funds carrying the SAME specific preferred theme | `max_per_specific_theme` (2) | per theme **value** |
| Max funds from the SAME specific preferred region | `max_per_specific_region` (2) | per region **value** |
| Max funds per provider | `max_per_provider` (5 → effectively off) | pass 2 |
| Max funds per asset category | `max_per_category` (5 → effectively off) | pass 2 |

The quotas count **per specific value**: covering two different preferred themes (one fund each) never blocks either theme; only the (quota+1)-th fund of the *same* theme or region is skipped. Skip events carry the live count, e.g. `theme:SUSTAINABILITY 2/2`.

**Count-restoring relaxation.** If the universe is too small to fill the portfolio under all constraints, a final logged relaxation (`caps_relaxed`) appends the best remaining funds regardless of caps — **completeness outranks diversification**. An additive append can never shrink the portfolio.

**ETF-only fallback.** If `etf_only` left fewer than 5 ETFs, remaining slots are filled from the scored active pool (risk-band filtered), labelled `etf_not_available` ("active fund — ETF not available within your criteria").

**Guarantee result.** Every preferred value is covered whenever the universe contains a carrier; values without any carrier are logged as `coverage_unfulfillable` with the reason ("no fund carrying this value in the universe" vs. "portfolio filled before this value could be covered").

#### Worked Example (real trace, real numbers)

Answers: aggressive · PREFER_ESG · prefer_etf · regions {germany, emerging_markets} · themes {sustainability, defense}. Universe: 64 funds → 41 eligible after filters.

| # | Fund | Base | Final | Decision |
|---|------|------|-------|----------|
| 1 | Deka MSCI Germany Climate Change ESG CTB ETF | 35.5 | 265.5 | **Pass 1** — matches theme sustainability + region germany |
| 2 | Deka MSCI World Climate Change ESG CTB ETF | 64.3 | 224.3 | **Pass 2** — next best score |
| 3 | Deka MSCI Europe Climate Change ESG CTB ETF | 56.1 | 216.1 | Skipped — `theme:SUSTAINABILITY 2/2` |
| 4 | Deka MSCI Japan Climate Change ESG CTB ETF | 51.7 | 211.7 | Skipped — `theme:SUSTAINABILITY 2/2` |
| 5 | Provinzial Aktien Welt | 92.1 | 182.1 | **Pass 2** — next best score |
| 7 | Amundi MSCI Emerging Markets UCITS ETF | 51.7 | 166.7 | **Pass 1** — matches region emerging_markets |
| 12 | Deka Europe Defense UCITS ETF | 41.7 | 156.7 | **Pass 1** — matches theme defense |

Result: 5 funds (ranks 1, 2, 5, 7, 12), **7/7 preference items fulfilled**. Ranks 3/4 are skipped (quota full) — never dropped, protected, or replaced. Rank 6 is simply not reached.

### Step 8 — Core/Satellite Classification *(v4 change)*

**v4 rationale:** A fund selected in pass 1 (coverage) should only be classified as **satellite** if it was chosen *solely because of* the preference match and would not have been selected by pass 2 quality ranking anyway. Funds matching preferences that are *also* top performers should be treated as **core** holdings with full allocations.

**Classification rule:**

1. **If the fund was selected in pass 2:** → **core** (selected by quality ranking).
2. **If the fund was selected in pass 1 AND its elevated score ranks it in the top `final_fund_count` (5) positions of the full ranking:** → **core** (would have been selected in pass 2 anyway; the preference match is incidental).
3. **If the fund was selected in pass 1 AND its elevated score does NOT rank it in the top 5:** → **satellite** (selected only because of coverage guarantee).

**Examples:**
- A sustainability-themed fund with elevated score ranking #1 selected in pass 1 → **core** (top performer).
- A defense-themed fund with elevated score ranking #12 selected in pass 1 → **satellite** (lower-ranked, coverage-driven).
- A fund selected in pass 2 → **core** regardless of theme.

Expected portfolio structure: 2–4 core positions, 0–3 satellites.

### Step 9 — Proportional Elevated-Score Allocation *(v4 change)*

**v4 rationale:** Allocations should reflect the relative quality (elevated score) of selected funds while respecting minimum allocations and satellite caps. This replaces the v3 inverse-volatility + tier bounds approach.

**Allocation method:**

1. **Identify allocation bands:**
   - If no satellites OR total satellite raw allocation ≤ 30 %: **single band** (all funds together)
   - If satellites exist AND would exceed 30 %: **two bands** (cores / satellites)

2. **Compute raw proportional weights** within each band:
   ```
   raw_weight[fund] = elevated_score[fund] / sum(elevated_score[band])
   ```

3. **Apply band caps** (two-band case only):
   - Satellite band: cap total at **30 %**
   - Core band: receives remaining **70 %**
   - Within each band, distribute proportionally by elevated score

4. **Floor enforcement** (Step 11): every fund ≥ `min_allocation_percentage` (10 %)
   - If infeasible (5 funds × 10 % minimum = 50 % minimum, always feasible for 5 funds), use equal split
   - Adjustments taken from funds above minimum, proportionally

5. **Integer rounding** (Step 11): round all allocations to whole percent; largest allocation absorbs remainder to ensure total = 100 %

**Configuration:**
- `min_allocation_percentage` = **10 %** (unchanged)
- `satellite_total_cap` = **30 %** (unchanged, but now applied as a band cap before proportional distribution)

**Key differences from v3:**
- v3: inverse-volatility weights + tier bounds (Core 1: 25–40 %, Core 2: 15–30 %, etc.) + regional tilt (×1.2)
- v4: elevated score proportional weights + satellite/core bands + no tier structure + no regional tilt

### Step 10 — Minimum Allocation Floor & Normalization

Apply the minimum allocation floor (`min_allocation_percentage` = 10 %) using a water-filling approach:

1. Ensure every fund ≥ 10 %
2. If the raw proportional weights already satisfy this, proceed to rounding
3. If any fund < 10 %, lift it to 10 % and reduce funds above the floor proportionally to their excess weight
4. If impossible (would require total > 100 %), fall back to equal split (20 % each for 5 funds)

After floor enforcement, normalize weights to sum to exactly 100 %.

### Step 11 — Output Rounding

Round all allocations to whole percent (integer values). The largest allocation absorbs the rounding remainder to guarantee total = 100 %.

---

## Risk Profile Reference

### Rationale

- **DEFENSIVE:** capital preservation; volatility ≤ 8 % keeps short-term fluctuations manageable; no high equity exposure.
- **BALANCED:** growth and stability weighted equally; SRRI 2–5 accepts short-term losses for medium-term returns.
- **OPPORTUNITY (Growth-Oriented):** return maximisation; no volatility upper bound, but a 10 % lower bound prevents filling the portfolio with low-risk assets.

### SRRI Alignment

| SRRI | Volatility (indicative) | Profile |
|------|------------------------|---------|
| 1 | < 0.5 % | Defensive |
| 2 | 0.5–2 % | Defensive |
| 3 | 2–5 % | Defensive / Balanced |
| 4 | 5–10 % | Balanced |
| 5 | 10–15 % | Balanced / Opportunity |
| 6 | 15–25 % | Opportunity |
| 7 | > 25 % | Opportunity |

---

## Preference Integration — Summary

| Preference | Value | Filter (Phase 1) | Boost (Phase 2) | Coverage (Step 7) | Allocation (Step 9) |
|------------|-------|------------------|-----------------|-------------------|----------------------|
| ESG | `ART_8_9_ONLY` | hard filter | — | — | — |
| ESG | `PREFER_ESG` | — | +6 (v3.2 tie-breaker) | — | — |
| ETF | `etf_only` | hard filter (+ fallback) | — | — | — |
| ETF | `prefer_etf` | — | +6 (v3.2 tie-breaker) | — | — |
| Region | values (e.g. `asia`) | — | 0 (disabled since v3.2) | pass-1 coverage; quota 2/value | *(v4: no tilt)* |
| Theme | values (e.g. `defense`) | — | 0 (disabled since v3.2) | pass-1 coverage; quota 2/value | satellite class (v4: intelligent) |

---

## Edge Case Handling (implemented behaviour)

| # | Case | Behaviour |
|---|------|-----------|
| 1 | Fewer than 5 eligible funds after all filters | Relaxations are gated by `min_candidates` (default 0 = off). The portfolio then contains as many funds as eligible; trace carries a warning below 3 funds. Selection never reduces the count further (invariant, see Step 7). |
| 2 | `etf_only` leaves fewer than 5 ETFs | Active-fund backfill, each labelled `etf_not_available`; relaxation entry `etf_only_fallback` in the trace. |
| 3 | Strong regional preference | Quota `max_per_specific_region` = 2 per value enforced as skip; coverage-beats-quota breach possible and logged; count restored via `caps_relaxed` only when the universe forces it. |
| 4 | Thematic funds increase portfolio risk | Handled structurally: satellites weigh ≥ 10 % each, satellite total ≤ 30 %, elevated-score weighting naturally down-weights lower scorers. (No per-theme MDD check is implemented.) |
| 5 | Many conflicting preferences / nearly empty intersection | Pass 1 covers every value that has a carrier anywhere; remaining slots fill with best funds; unsatisfiable values are logged (`coverage_unfulfillable`) with reason. No preference "hierarchy relaxation" is needed because no fund is ever evicted. |
| 6 | More preferred values than slots | Values are satisfied in quality order of their best carrier; the rest surface as unfulfilled preference items in `preference_satisfaction` (7-item per-item report). |
| 7 | All selected funds are pass-1 coverage picks AND all rank outside top 5 | All classified as satellites; if total > 30 %, satellite band is capped at 30 % and allocations distributed proportionally within that band. Core band would be empty (special case: single-band allocation). |
| 8 | Sustainability fund is top-ranked AND selected in pass 1 | Classified as **core** (v4); receives proportional elevated-score allocation in core band, not downgraded to satellite allocation. |

---

## Decision Trace & Explainability

Every stage is recorded in `decision_trace` and rendered in the GUI (Preferences tab). Selection events, in execution order:

| Event | Meaning |
|-------|---------|
| `pass1_select` | Coverage pick; carries `matched` [{dimension, value}…], `also_satisfies`, optional `quota_breached` |
| `pass2_select` | Fill pick (next best score) |
| `selection_skip` | Skip in pass 2; `reason` ∈ {`provider_cap`, `category_cap`, `theme_quota`, `region_quota`}; `dimensions` carries live counts (`theme:SUSTAINABILITY 2/2`) |
| `coverage_unfulfillable` | Preferred value not covered; `reason`: no carrier in universe / portfolio filled first |
| `caps_relaxed` | Count-restoring relaxation; lists added ISINs |
| `etf_fallback_fill` | Active fund filled an ETF-only slot |
| **v4:** `core_satellite_classification` | *(new)* Records classification decision for each fund: `core_top_performer` (pass 1 but ranks top 5), `core_quality_selected` (pass 2), `satellite_coverage_only` (pass 1, ranks outside top 5) |

Ranking candidates carry a status: `selected` (pass 2), `selected_pass1_coverage` (pass 1), `skipped_provider_cap`, `skipped_category_cap`, `skipped_theme_quota`, `skipped_region_quota`, `not_reached`.

---

## Engine Configuration (defaults)

| Parameter | Default | Effect |
|-----------|---------|--------|
| `min_candidates` | 0 | disables all filter relaxations |
| `top_k` | 65 | pass-2 pool = full universe (capping off) |
| `final_fund_count` | 5 | portfolio size |
| `max_per_provider` | 5 | provider cap effectively off |
| `max_per_category` | 5 | category cap effectively off |
| `max_per_specific_theme` | 2 | quota per preferred theme value |
| `max_per_specific_region` | 2 | quota per preferred region value |
| `min_allocation_percentage` | 10 | per-fund weight floor |
| `satellite_total_cap` | 30 | *(v4: percentage)* satellite band cap |
| `BOOST_ELEVATORS` | ETF 6 / ESG 6 / Region 0 / Theme 0 | Step 6 boosts (all tie-breaker-level; preferences honored structurally — see rationale) |
| `thematic_guarantee` / `regional_guarantee` | True / True | gate pass 1 per dimension |
| `theme_cap` / `regional_cap` | True / True | gate the per-value quotas |

---

## Data Requirements

| Field | Used In |
|-------|---------|
| `srri` (or `risk_level`) | risk band, proxies |
| `volatility` (annual %) | risk band |
| `max_drawdown` | risk band, scoring |
| `yearly_fee` | scoring (TER) |
| `sharpe_ratio` | scoring |
| `is_etf` | ETF filter/boost |
| `esg_label` | ESG filter/boost |
| `region` | region boost, coverage |
| `theme` | theme boost, coverage, core/satellite class |
| `asset_class` | category cap |
| `provider` | provider cap |

---

## Change Log vs. v3

| Aspect | v3 | v4 (this spec) |
|--------|----|----------------|
| **Core/Satellite classification** | Theme set and ≠ `NONE` → satellite | **Pass-1 fund is satellite ONLY IF elevated score ranks it outside top 5** (intelligent classification) |
| **Allocation method** | Inverse-volatility weights + tier bounds (Core 1: 25–40 %, Core 2: 15–30 %, Core 3: 10–25 %, Core 4+: 10–15 %, Satellite: 10–15 %) + regional tilt (× 1.2) | **Proportional elevated-score weights** with satellite/core band caps (satellite ≤ 30 %, cores get remainder); no tiers, no regional tilt |
| **Allocation steps** | Step 9: tier bounds + inverse-vol; Step 10: regional tilt; Step 11: satellite cap; Step 12: floor + rounding | Step 9: proportional by elevated score + bands; Step 10: floor + normalize; Step 11: rounding |
| **Sustainability funds** | Always satellite if theme set (even if top performer) | **Core if top-5 ranked** (v4: no allocation penalty for high-performing thematic funds) |
| **Trace events** | Selection events only | *(v4 adds)* `core_satellite_classification` with reasoning |
| Selection | Two-pass additive | (unchanged) |
| Scoring, filters, risk bands, boosts | — | (unchanged from v3) |

---

## v4 Implementation Notes

**Key logic changes required in [`decision_engine.py`](funds_portfolio/portfolio/decision_engine.py):**

1. **Step 8 — Classification:**
   - After selection, determine top-5 funds by elevated score from full ranking
   - For each pass-1 selected fund: check if its ranking position ≤ `final_fund_count` (5)
   - Classify accordingly: `core_top_performer` / `core_quality_selected` / `satellite_coverage_only`

2. **Step 9 — Allocation:**
   - Remove inverse-volatility weighting, tier bounds, regional tilt logic
   - Implement proportional elevated-score allocation:
     - Single-band if no satellites OR satellites ≤ 30 % raw
     - Two-band (cores 70 % / satellites 30 %) otherwise
   - Distribute proportionally by elevated score within each band

3. **Step 10 — Floor:**
   - Apply 10 % floor via water-filling
   - Fall back to equal split if infeasible

4. **Step 11 — Rounding:**
   - Integer rounding, largest absorbs remainder

5. **Trace logging:**
   - Add `core_satellite_classification` event with fund-by-fund reasoning
   - Update allocation trace to reflect new proportional method

**Backward compatibility:** v3 parameters (`tier_bounds`, `regional_tilt_factor`) become unused but can remain in config for graceful migration.

---

## Validation Criteria

The v4 implementation should satisfy:

1. **Classification correctness:** High-scoring sustainability funds selected in pass 1 are classified as core, not satellite
2. **Allocation proportionality:** Core funds with higher elevated scores receive higher allocations (within constraints)
3. **Satellite cap enforcement:** Total satellite allocation ≤ 30 % in all cases
4. **Minimum floor:** Every fund ≥ 10 % (or equal split if infeasible)
5. **Integer allocations:** All weights are whole percent, sum = 100 %
6. **Count safety:** (unchanged) Portfolio always contains exactly `final_fund_count` (5) funds when universe permits
7. **Trace completeness:** Classification reasoning logged for every fund

**Recommended test cases:**
- Sustainability fund ranks #1, selected pass 1 → core, high allocation
- Defense fund ranks #12, selected pass 1 → satellite, capped allocation
- 3 satellites (all rank >5) → satellite band 30 %, core band 70 %
- 1 satellite + 4 cores → single-band proportional (no artificial 30 % cap)
