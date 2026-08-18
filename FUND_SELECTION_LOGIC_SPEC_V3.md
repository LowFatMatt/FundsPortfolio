# Fund Selection Logic — Specification v3
**Source:** Provinzial "Fondsauswahllogik – Fondskompass" (March 2026); v2 reworked 2026-08-17/18
**Implementation:** [`funds_portfolio/portfolio/decision_engine.py`](funds_portfolio/portfolio/decision_engine.py)
**Predecessor:** v2 archived at [`notes/FUND_SELECTION_LOGIC_SPEC_V2.md`](notes/FUND_SELECTION_LOGIC_SPEC_V2.md)

> **v3 headline change:** fund *selection* is now a **two-pass, coverage-first, purely additive**
> walk over a single ranking (Step 7). The v2 mechanisms "force-insert guarantee with
> protection set" and "post-selection caps with drops" are removed. Quotas are enforced
> as *skips during selection*, never as drops after it, which makes the portfolio count
> safe by construction.

---

## Overview

The fund selection logic operates in three sequential phases, each fully recorded in a
machine-readable decision trace:

| Phase | Goal | Output |
|-------|------|--------|
| **1 — Filter** | Exclude ineligible funds (data quality, ESG, ETF, risk band) | Reduced fund universe |
| **2 — Scoring** | Score remaining funds: quantitative base + preference boosts | Single ranked list (the ranking) |
| **3 — Portfolio Construction** | Two-pass selection of 5 funds, then Core-Satellite weighting | 5-fund portfolio with allocations + full decision log |

---

## Phase 1 — Filter

Funds pass sequential hard filters before being admitted to scoring. The trace records
each filter with before/after counts.

### Step 0 — Required Fields Filter

Exclude funds lacking any of: `isin`, `name`, `yearly_fee`, `sharpe_ratio`,
`max_drawdown`, `srri` (or `risk_level`), `volatility`. Regulatory distribution status
(approval for Germany, not in wind-down) is guaranteed upstream by database curation.

> Fallbacks in later stages tolerate single missing metrics (SRRI proxies, Step 5), but
> the required-fields gate keeps the universe data-complete.

### Step 1 — ESG Filter

ESG is a single three-case preference (`esg_preference`); Article 8 and 9 count together
as "sustainable" (derived from `esg_label`):

- **`ART_8_9_ONLY`** — hard filter: keep only `SFDR_ARTICLE_8` / `SFDR_ARTICLE_9`.
- **`PREFER_ESG`** — no exclusion here; sustainable funds get a scoring boost (Step 6).
- **`NONE`** — ESG ignored entirely (legacy answer values are normalised to these three).

### Step 2 — ETF Preference Filter

- **`etf_only`** — hard filter: keep only `is_etf` funds. If fewer than 5 ETFs remain
  after all filters, the ETF-only fallback (Step 7, end) fills the remaining positions
  with active funds.
- **`prefer_etf`** — no exclusion; ETFs get a scoring boost (Step 6).
- **`no_preference`** — no action.

### Step 3 — Risk Band Filter

Map `risk_approach` (conservative / moderate / aggressive) to a three-tier profile and
apply the bands of the authoritative slide (Step 8 of the source deck):

| Parameter | DEFENSIVE | BALANCED | OPPORTUNITY *(= Growth-Oriented)* |
|-----------|-----------|----------|-----------------|
| SRRI (or `risk_level`) | 1–3 | 2–5 | 4–7 |
| Annual volatility | ≤ 8 % | 5–15 % | ≥ 10 % (no upper bound) |
| Max Drawdown | < 15 % | < 30 % | < 50 % |

Bands intentionally overlap to avoid abrupt exclusion at boundaries.

### Step 4 — Regional & Thematic Preferences *(soft — no filter)*

Region and theme preferences never exclude funds. They act through (a) scoring boosts
(Step 6), (b) the coverage pass (Step 7, pass 1), and (c) the allocation tilt (Step 10).

### Relaxations and Warnings *(gated by `min_candidates`)*

- **Risk-band relaxation:** if fewer than `min_candidates` funds remain, widen the band
  by ±1 SRRI and ±5 % volatility. Currently **disabled** (`min_candidates = 0`), so an
  over-restrictive universe falls through honestly instead of silently widening.
- **Final-fund floor:** with `min_candidates > 0`, if the risk band leaves fewer than 5
  funds but the pre-risk pool has enough, revert to the pre-risk pool (also disabled by
  default).
- **Universe warning:** if 0 < remaining < 3, the trace carries a warning that the
  portfolio may contain funds at the edge of the suitability range.

---

## Phase 2 — Scoring

### Step 5 — Base Quality Score (0–100)

Each eligible fund receives a composite score from three min-max normalised metrics
(normalisation spans the eligible universe of the current session, scale 0–10):

```
base = (Sharpe_norm × 5.0) + (MDD_norm × 3.0) + (TER_norm × 2.0)
```

| Component | Metric | Weight | Direction |
|-----------|--------|--------|-----------|
| Risk-adjusted return | Sharpe Ratio | 50 % | higher is better |
| Drawdown protection | Maximum Drawdown | 30 % | lower is better (inverted) |
| Cost efficiency | TER (`yearly_fee`) | 20 % | lower is better (inverted) |

Proxies when a metric is missing at scoring time: MDD ← `SRRI_MDD_PROXY[srri]`,
volatility ← `SRRI_VOL_PROXY[srri]` (used in allocation).

**Ranking sort order** (deterministic): final score ↓, then Sharpe ↓, then fee ↑, then
ISIN ↓.

### Step 6 — Preference Boosts (on top of base)

Boosts are deliberately large so preferences can reorder the ranking; the coverage pass
(Step 7) — not the boost — *guarantees* preference coverage.

| Boost | Condition | Value (default `BOOST_ELEVATORS`) |
|-------|-----------|------|
| ETF | `prefer_etf` and fund `is_etf` | **+45** |
| ESG | `PREFER_ESG` and `esg_label` ∈ {Art. 8, 9} | **+45** |
| Region | `fund.region` exactly in `preferred_regions` | **+70** |
| Theme | `fund.theme` in `preferred_themes` (placeholder `NONE` disables) | **+70** |

`ART_8_9_ONLY` is a hard filter only (no boost). A fund can accumulate multiple boosts
(e.g. Region + Theme + ETF + ESG).

---

## Phase 3 — Portfolio Construction

### Step 7 — Selection: Two-Pass, Coverage-First, Purely Additive

Selection operates on the single ranked list and only ever **adds** funds. No fund is
dropped, protected, or swapped after being selected — the portfolio size can only grow
toward `final_fund_count` (5). The count is safe by construction.

**Pass 1 — coverage (preferences first).** Walk the *full* ranking in quality order and
select a fund only if it matches at least one **still-unsatisfied** preferred region or
theme. Stop when every preferred value is covered, no candidate exists anywhere in the
ranking, or the portfolio is full.

- The guarantee toggles gate pass 1 per dimension: `thematic_guarantee` (themes),
  `regional_guarantee` (regions). Defaults: on.
- One pick can satisfy several values at once (fund carries a preferred region *and*
  theme); the collateral match is recorded as `also_satisfies`.
- Quota-compliant candidates are preferred (sweep A). If a preferred value remains
  unsatisfied and the only carrying fund would breach its quota, **coverage beats
  quota**: the best such fund is selected and the breach is logged explicitly (sweep B).

**Pass 2 — fill (best remaining).** Restart at the top of the `top_k` pool — excluding
funds already selected in pass 1 (the effective pool is smaller than `top_k`) — and fill
the remaining slots with the best funds regardless of preference match, subject to the
constraints below.

**Constraints — enforced as skips during selection, never as drops after it:**

| Constraint | Parameter (default) | Scope |
|------------|---------------------|-------|
| Max funds carrying the SAME specific preferred theme | `max_per_specific_theme` (2) | per theme **value** |
| Max funds from the SAME specific preferred region | `max_per_specific_region` (2) | per region **value** |
| Max funds per provider | `max_per_provider` (5 → effectively off) | pass 2 |
| Max funds per asset category | `max_per_category` (5 → effectively off) | pass 2 |

The quotas count **per specific value**: covering two different preferred themes (one
fund each) never blocks either theme; only the (quota+1)-th fund of the *same* theme or
region is skipped. Skip events carry the live count, e.g. `theme:SUSTAINABILITY 2/2`.

**Count-restoring relaxation.** If the universe is too small to fill the portfolio under
all constraints, a final logged relaxation (`caps_relaxed`) appends the best remaining
funds regardless of caps — **completeness outranks diversification**. An additive append
can never shrink the portfolio.

**ETF-only fallback.** If `etf_only` left fewer than 5 ETFs, remaining slots are filled
from the scored active pool (risk-band filtered), labelled
`etf_not_available` ("active fund — ETF not available within your criteria").

**Guarantee result.** Every preferred value is covered whenever the universe contains a
carrier; values without any carrier are logged as `coverage_unfulfillable` with the
reason ("no fund carrying this value in the universe" vs. "portfolio filled before this
value could be covered").

#### Worked Example (real trace, real numbers)

Answers: aggressive · PREFER_ESG · prefer_etf · regions {germany, emerging_markets} ·
themes {sustainability, defense}. Universe: 64 funds → 41 eligible after filters.

| # | Fund | Base | Final | Decision |
|---|------|------|-------|----------|
| 1 | Deka MSCI Germany Climate Change ESG CTB ETF | 35.5 | 265.5 | **Pass 1** — matches theme sustainability + region germany |
| 2 | Deka MSCI World Climate Change ESG CTB ETF | 64.3 | 224.3 | **Pass 2** — next best score |
| 3 | Deka MSCI Europe Climate Change ESG CTB ETF | 56.1 | 216.1 | Skipped — `theme:SUSTAINABILITY 2/2` |
| 4 | Deka MSCI Japan Climate Change ESG CTB ETF | 51.7 | 211.7 | Skipped — `theme:SUSTAINABILITY 2/2` |
| 5 | Provinzial Aktien Welt | 92.1 | 182.1 | **Pass 2** — next best score |
| 7 | Amundi MSCI Emerging Markets UCITS ETF | 51.7 | 166.7 | **Pass 1** — matches region emerging_markets |
| 12 | Deka Europe Defense UCITS ETF | 41.7 | 156.7 | **Pass 1** — matches theme defense |

Result: 5 funds (ranks 1, 2, 5, 7, 12), **7/7 preference items fulfilled**. Ranks 3/4
are skipped (quota full) — never dropped, protected, or replaced. Rank 6 is simply not
reached.

### Step 8 — Core/Satellite Classification

`theme` set and ≠ `NONE` → **satellite**; otherwise **core**. Expected structure:
2–4 core positions, 0–3 satellites (satellite total weight capped, Step 11).

### Step 9 — Tiered Weight Bounds & Inverse-Volatility Weights

Raw weights are inverse-volatility (`1/vol`, SRRI proxy when `volatility` is missing),
then clipped to tier bounds:

| Position | Min | Max |
|----------|-----|-----|
| Core 1 (best core) | 25 % | 40 % |
| Core 2 | 15 % | 30 % |
| Core 3 | 10 % | 25 % |
| Core 4+ | 10 % | 15 % |
| Satellite (flat) | 10 % | 15 % |

### Step 10 — Regional Tilt

Funds whose `region` is a preferred region get a **relative +20 % weight increase
(× 1.2)**, capped at their tier maximum.

### Step 11 — Satellite Cap & Normalisation

Weights are normalised to 100 %; the satellite total is capped at **30 %** (re-enforced
after normalisation; the freed headroom goes to cores only, up to their maxima).

### Step 12 — Minimum Allocation & Output Rounding

A water-filling floor guarantees every fund ≥ `min_allocation_percentage` (10 %);
if infeasible for the fund count, an equal split is used. Allocations are rounded to
whole percent; the largest position absorbs the rounding remainder (total = 100 %).

> The 10 % floor holds after clipping but — with several satellites — the satellite cap
> and normalisation can in practice scale individual funds below it; the water-filling
> floor is applied last and restores it where feasible.

---

## Risk Profile Reference

### Rationale

- **DEFENSIVE:** capital preservation; volatility ≤ 8 % keeps short-term fluctuations
  manageable; no high equity exposure.
- **BALANCED:** growth and stability weighted equally; SRRI 2–5 accepts short-term
  losses for medium-term returns.
- **OPPORTUNITY (Growth-Oriented):** return maximisation; no volatility upper bound, but
  a 10 % lower bound prevents filling the portfolio with low-risk assets.

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

| Preference | Value | Filter (Phase 1) | Boost (Phase 2) | Coverage (Step 7) | Allocation (Step 10) |
|------------|-------|------------------|-----------------|-------------------|----------------------|
| ESG | `ART_8_9_ONLY` | hard filter | — | — | — |
| ESG | `PREFER_ESG` | — | +45 | — | — |
| ETF | `etf_only` | hard filter (+ fallback) | — | — | — |
| ETF | `prefer_etf` | — | +45 | — | — |
| Region | values (e.g. `asia`) | — | +70 | pass-1 coverage; quota 2/value | × 1.2 tilt |
| Theme | values (e.g. `defense`) | — | +70 | pass-1 coverage; quota 2/value | satellite class |

---

## Edge Case Handling (implemented behaviour)

| # | Case | Behaviour |
|---|------|-----------|
| 1 | Fewer than 5 eligible funds after all filters | Relaxations are gated by `min_candidates` (default 0 = off). The portfolio then contains as many funds as eligible; trace carries a warning below 3 funds. Selection never reduces the count further (invariant, see Step 7). |
| 2 | `etf_only` leaves fewer than 5 ETFs | Active-fund backfill, each labelled `etf_not_available`; relaxation entry `etf_only_fallback` in the trace. |
| 3 | Strong regional preference | Quota `max_per_specific_region` = 2 per value enforced as skip; coverage-beats-quota breach possible and logged; count restored via `caps_relaxed` only when the universe forces it. |
| 4 | Thematic funds increase portfolio risk | Handled structurally: satellites weigh 10–15 % each, satellite total ≤ 30 %, inverse-volatility weighting damps volatile funds. (No per-theme MDD check is implemented.) |
| 5 | Many conflicting preferences / nearly empty intersection | Pass 1 covers every value that has a carrier anywhere; remaining slots fill with best funds; unsatisfiable values are logged (`coverage_unfulfillable`) with reason. No preference "hierarchy relaxation" is needed because no fund is ever evicted. |
| 6 | More preferred values than slots | Values are satisfied in quality order of their best carrier; the rest surface as unfulfilled preference items in `preference_satisfaction` (7-item per-item report). |

---

## Decision Trace & Explainability

Every stage is recorded in `decision_trace` and rendered in the GUI (Preferences tab).
Selection events, in execution order:

| Event | Meaning |
|-------|---------|
| `pass1_select` | Coverage pick; carries `matched` [{dimension, value}…], `also_satisfies`, optional `quota_breached` |
| `pass2_select` | Fill pick (next best score) |
| `selection_skip` | Skip in pass 2; `reason` ∈ {`provider_cap`, `category_cap`, `theme_quota`, `region_quota`}; `dimensions` carries live counts (`theme:SUSTAINABILITY 2/2`) |
| `coverage_unfulfillable` | Preferred value not covered; `reason`: no carrier in universe / portfolio filled first |
| `caps_relaxed` | Count-restoring relaxation; lists added ISINs |
| `etf_fallback_fill` | Active fund filled an ETF-only slot |

Ranking candidates carry a status: `selected` (pass 2), `selected_pass1_coverage`
(pass 1), `skipped_provider_cap`, `skipped_category_cap`, `skipped_theme_quota`,
`skipped_region_quota`, `not_reached`.

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
| `BOOST_ELEVATORS` | ETF 45 / ESG 45 / Region 70 / Theme 70 | Step 6 boosts |
| `thematic_guarantee` / `regional_guarantee` | True / True | gate pass 1 per dimension |
| `theme_cap` / `regional_cap` | True / True | gate the per-value quotas |

---

## Data Requirements

| Field | Used In |
|-------|---------|
| `srri` (or `risk_level`) | risk band, proxies |
| `volatility` (annual %) | risk band, inverse-vol weighting |
| `max_drawdown` | risk band, scoring |
| `yearly_fee` | scoring (TER) |
| `sharpe_ratio` | scoring |
| `is_etf` | ETF filter/boost |
| `esg_label` | ESG filter/boost |
| `region` | region boost, coverage, tilt |
| `theme` | theme boost, coverage, core/satellite class |
| `asset_class` | category cap |
| `provider` | provider cap |

---

## Change Log vs. v2

| Aspect | v2 | v3 (this spec) |
|--------|----|----------------|
| Selection | top-5 pick + force-insert guarantees with protected set + post-selection caps (drops) | **two-pass coverage-first additive selection; no drops, no protection set** |
| Preference coverage | guarantee swaps (could starve, could shrink portfolio) | **pass 1 structural; count-safe** |
| Diversification caps | destructive drops after selection | **skips during selection + count-restoring relaxation** |
| Quota semantics | max 2 same preferred region/theme (drop) | same values, per **specific** value (`max_per_specific_theme` / `max_per_specific_region`), enforced as skip with live count in trace |
| Boosts | ETF +5 / ESG +5 / Region +3 / Theme +3 | **ETF +45 / ESG +45 / Region +70 / Theme +70** (coverage guaranteed by pass 1, boosts only steer ranking) |
| Count safety | not guaranteed (5→3 bug observed) | **guaranteed by construction** (validated: 0 selection-limited portfolios on the 1691-answer grid) |
| Trace vocabulary | `thematic_insert`, `regional_insert`, `*_cap_drop` | `pass1_select`, `pass2_select`, `selection_skip`, `coverage_unfulfillable`, `caps_relaxed` |
| Relaxations | always-on widening | gated by `min_candidates` (default off) |
| Scoring, filters, allocation, risk bands | — | unchanged from v2 |
