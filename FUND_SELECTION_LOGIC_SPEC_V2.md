# Fund Selection Logic — Specification v2
**Source:** Provinzial "Fondsauswahllogik – Fondskompass" (March 2026)

---

## Overview

The fund selection logic operates in three sequential phases:

| Phase | Goal | Output |
|-------|------|--------|
| **1 — Filter** | Exclude ineligible funds based on fixed criteria (risk profile, ESG, ETF, preferences) | Reduced fund universe |
| **2 — Scoring** | Score remaining funds using a quantitative quality model | Ranked fund list with scores |
| **3 — Portfolio Construction** | Select top 5 funds and set portfolio weights | 5-fund portfolio with allocations |

---

## Phase 1 — Filter

Funds pass through **5 sequential hard filters** before being admitted to scoring.

### Step 0 — Regulatory & Data Quality Filter *(non-negotiable precondition)*

Exclude all funds that fail basic eligibility:

- Fund must be approved for distribution in Germany
- Fund must have a valid, current SRRI rating (1–7)
- Required data fields must be populated: **volatility**, **TER**, **Sharpe Ratio**, **MDD**
- Fund must not be in wind-down, provisional closure, or suspension

**Purpose:** Ensure only legally distributable, data-complete, and operationally active funds are considered.

### Step 1 — Risk Profile Filter

Match fund characteristics against the user's selected risk profile. Exclude funds outside the defined bands:

- Check fund **volatility** against the allowed range for the profile
- Check **SRRI rating** against acceptable SRRI levels for the profile
- Check **maximum drawdown (MDD)** against the tolerance threshold

**Purpose:** Suitability assurance per IDD obligations. Only funds whose risk characteristics are compatible with the customer's risk tolerance pass.

### Step 2 — ESG Filter

Apply the user's stated sustainability preferences per IDD Article 9 requirements:

- **ESG compliance required:** Exclude all funds without a positive ESG rating or ESG classification
- **Specific ESG level required (e.g. SFDR Article 8 or Article 9):** Exclude funds not meeting that classification
- **No ESG preference stated:** No exclusions at this step (ESG may still influence scoring in Step 6)

**Purpose:** Mandatory compliance with IDD sustainability preference integration.

### Step 3 — ETF Preference Filter

Apply the user's stated ETF preference:

- **ETFs only:** Exclude all non-ETF (actively managed) funds — hard filter
- **Prefer ETFs:** No exclusions; ETF preference is handled as a scoring bonus in Step 6 — soft preference
- **No preference:** No action

**Purpose:** Explicit product-type constraints are enforced before quality scoring begins.

### Step 4 — Regional & Thematic Focus Filter *(soft filter)*

Apply regional and thematic preferences as soft markers — no hard exclusions:

- **Region preference:** Mark matching funds as preferred; do not exclude others unless the portfolio can fully satisfy the preference
- **Theme preference:** Mark matching thematic funds for a scoring bonus and satellite positioning
- **No hard exclusions are applied in this step**

**Purpose:** Capture user personalisation preferences without compromising diversification. Regional and thematic preferences are handled primarily through scoring and allocation adjustments.

---

## Phase 2 — Scoring

### Step 5 — Fund Quality Scoring

Each fund that passes Steps 0–4 receives a **composite quality score (0–100)** based on three weighted metrics.

#### Scoring Components

| Component | Metric | Weight | Rationale |
|-----------|--------|--------|-----------|
| Risk-Adjusted Return | Sharpe Ratio | **50 %** | Primary measure of return per unit of total risk; standard for cross-fund comparison |
| Drawdown Protection | Maximum Drawdown (MDD) | **30 %** | Captures worst-case loss scenario; directly affects customer experience and IDD risk disclosure |
| Cost Efficiency | TER (Total Expense Ratio) | **20 %** | Lower costs compound significantly over typical contract durations of 10–30 years |

> **Note:** Return consistency was considered but excluded from the model because many funds in a ~200-fund universe may lack sufficient history for reliable rolling calculations (particularly for ProAM funds). This metric is a candidate for a future extension.

#### Normalisation Approach

Each metric is min-max normalised across the full eligible fund universe for the current user session onto a 0–10 scale:

```
normalised_value = (value − min) / (max − min) × 10
```

For Maximum Drawdown (lower is better), the formula is inverted:

```
normalised_mdd = (max − value) / (max − min) × 10
```

#### Composite Score Formula

```
score = (Sharpe_norm × 5.0) + (MaxDD_norm × 3.0) + (TER_inv_norm × 2.0)
```

The raw score range is 0–100.

#### Scoring Example

| Fund | Sharpe Norm | MaxDD Norm | TER Norm | Raw Score | Preference Adj | Reason | Final Score |
|------|-------------|------------|----------|-----------|----------------|--------|-------------|
| Fund A | 8.2 | 9.1 | 6.8 | 79.25 | +5 | ESG | 84.25 |
| Fund B | 7.8 | 7.2 | 9.5 | 80.70 | +3 | Region | 83.70 |
| Fund C | 6.5 | 8.8 | 8.2 | 73.75 | +5 | ETF | 78.75 |
| Fund D | 9.0 | 6.5 | 5.5 | 73.00 | 0 | — | 73.00 |
| Fund E | 5.8 | 9.5 | 9.0 | 72.30 | +3 | Theme | 75.30 |

### Step 6 — Preference Score Adjustment

Apply scoring bonuses according to user preferences **after** the base quality score is computed:

| Preference | Condition | Bonus |
|------------|-----------|-------|
| ETF | "Prefer ETFs" selected | +5 pts for all ETF funds |
| ESG | ESG preference active but not a mandatory filter | +5 pts for all ESG funds |
| Region | Matching preferred region | +3 pts per fund per matching region |
| Theme | Matching preferred theme | +3 pts per fund per matching theme |

The adjusted score is used for final ranking.

### Step 7 — Top 5 Selection

Rank all scored funds descending by adjusted total score. Select the top 5, subject to **diversification constraints**:

- Maximum **2 funds from the same sub-category** (e.g. two large-cap equity funds)
- Maximum **1 fund from the same fund provider** (unless the fund universe makes this unavoidable — TBD)
- If thematic preferences were selected: **at least 1 thematic fund must be included**, provided such a fund passed all filters

**Purpose:** Prevent over-concentration and ensure a balanced, diversified 5-fund portfolio built from genuinely differentiated building blocks.

---

## Phase 3 — Portfolio Construction

### Portfolio Allocation Logic

Once the top 5 funds are selected, weights are determined using a **Core-Satellite approach combined with inverse volatility weighting**. The method is transparent, defensible to regulators, and produces intuitive weights understandable to customers.

#### 4-Step Allocation Process

**Step 1: Classify each fund as Core or Satellite**

| Class | Description | Count |
|-------|-------------|-------|
| **Core** | Broadly diversified funds matching the risk profile (e.g. multi-asset, balanced equity, bond funds) | 2–4 positions |
| **Satellite** | Thematic, regional specialist, or single-factor funds | 0–3 positions (max 30 % total weight) |

**Step 2: Assign base weight ranges**

| Position | Min Weight | Max Weight | Avg Weight |
|----------|------------|------------|------------|
| Core 1 (highest quality score) | 25 % | 40 % | 30–35 % |
| Core 2 | 15 % | 30 % | 20–25 % |
| Core 3 | 10 % | 25 % | 15–20 % |
| Core 4 (if applicable) | 10 % | 15 % | 10–15 % |
| Satellite (if applicable) | 10 % | 15 % | 10 % |

**Step 3: Apply inverse volatility adjustment**

Within the weight ranges above, final weights are adjusted using inverse volatility:

```
weight_i = (1 / vol_i) / sum(1 / vol_j  for all j in portfolio)
```

The resulting weight is clipped to the min/max bounds defined in Step 2.

> Inverse volatility naturally tilts the portfolio toward lower-risk funds — appropriate for the insurance context.

**Step 4: Apply regional tilt (if applicable)**

If the user selected regional preferences, funds matching the preferred region receive a **relative weight increase of +20 %** (i.e. × 1.2), capped at the maximum weight for their classification.

#### Allocation by Risk Profile

| Profile | Typical Structure | Satellite Allocation | Notes |
|---------|-------------------|----------------------|-------|
| **Defensive** | 4–5 Core positions, bonds, mixed funds | 0 % or 10 % | Capital preservation priority; satellite limited to contain volatility |
| **Balanced** | 3–4 Core positions | 10–20 % | Moderate growth target allows meaningful satellite exposure |
| **Growth-Oriented** | 2–3 Core positions, equity focus | Up to 30 % | Growth maximisation allows higher thematic/regional satellite weights |

#### Example Portfolio

**User selection:** Balanced | ESG: no preference | ETF: preferred | Region: Europe | Theme: Technology

| Fund | Type | Classification | Volatility | Quality Score | Weight |
|------|------|----------------|------------|---------------|--------|
| Provinzial Aktien Welt | ETF | Core 1 | 12.3 % | 84.0 | 30 % |
| Flossbach v. Storch Multiple Opp. | Active | Core 2 | 10.8 % | 83.5 | 25 % |
| DWS Concept Kaldemorgen | Active | Core 3 | 9.5 % | 78.3 | 20 % |
| Xtrackers MSCI World ETF | ETF | Core 4 | 14.1 % | 74.2 | 15 % |
| Pictet Digital SMAC Technology | Active | Satellite | 18.7 % | 76.1 | 10 % |

---

## Risk Profile Reference

### Risk Profile Thresholds

| Parameter | Defensive | Balanced | Growth-Oriented |
|-----------|-----------|----------|-----------------|
| Annual Volatility | 0–8 % | 5–15 % | 10–30 % (+) |
| SRRI Rating | 1–3 | 2–5 | 4–7 |
| Max Drawdown (MDD) | < 15 % | < 30 % | < 50 % |
| Asset Categories | Bond funds, money market-like funds ~~mixed funds~~ | Capital protection funds, bond funds, equity funds, asset management funds ~~mixed funds~~, index funds (ETFs) | Equity funds, asset management funds, index funds (ETFs) |

> **Note:** Thresholds intentionally overlap slightly (e.g. volatility 5–8 % applies to both Defensive and Balanced). This ensures smooth transitions and avoids abrupt exclusion at boundaries. Funds in the overlap zone receive the highest quality score for that profile, regardless of nominal profile assignment.

### Profile Rationale

**Defensive:** Primary objective is capital preservation and income. High equity exposure is incompatible. Volatility capped at 8 % to keep short-term fluctuations manageable.

**Balanced:** Growth and stability weighted equally. Moderate equity allocation and SRRI 2–5 reflect willingness to accept short-term losses in exchange for medium-term returns.

**Growth-Oriented:** Primary objective is return maximisation. The customer accepts significant short-term volatility and losses for higher long-term returns. No volatility upper bound, but a minimum of 10 % volatility ensures this profile is not filled with low-risk assets.

> Thresholds are calibrated to align with common practice in the German insurance market and with investor risk categories defined under MiFID-equivalent suitability assessment regulations.

### SRRI Alignment Table

| SRRI Level | Volatility Range | Risk Profile |
|------------|-----------------|--------------|
| 1 | < 0.5 % | Defensive |
| 2 | 0.5–2 % | Defensive |
| 3 | 2–5 % | Defensive / Balanced |
| 4 | 5–10 % | Balanced |
| 5 | 10–15 % | Balanced / Growth-Oriented |
| 6 | 15–25 % | Growth-Oriented |
| 7 | > 25 % | Growth-Oriented |

---

## Preference Matching Logic — Summary Table

User preferences are integrated at two points: as hard filters in Phase 1 and as score adjustments in Phase 2.

| Preference | Selection | Action | Stage |
|------------|-----------|--------|-------|
| ESG | ESG-compliant required | Hard filter: exclude all non-ESG funds | Phase 1 |
| ESG | Prefer ESG | Soft boost: +5 pts for ESG funds | Phase 2 |
| ESG | No preference | No action | — |
| ETF | 100 % ETFs | Hard filter: exclude all active funds | Phase 1 (Step 3) |
| ETF | Prefer ETFs | Soft boost: +5 pts for all ETFs | Phase 2 (Step 6) |
| ETF | No preference | No action | — |
| Region | Focus region selected | Soft tilt: +3 pts per region; allocation weight adjusted | Phase 2 |
| Region | No preference | No action | — |
| Theme | Focus theme selected | Soft boost: +3 pts; satellite position reserved | Phase 2 |
| Theme | No preference | No action | — |

### ESG Logic Detail

When no ESG preference is stated:
- Funds with ESG rating receive a **+5 pt bonus** on their total score
- ESG classification may serve as a **tiebreaker** when multiple funds have equal total scores
- ESG classification (SFDR Article 8 / 9) is displayed in the explainability layer for advisers

### ETF Logic Detail

- **ETFs only:** Significantly restricts the eligible universe. Edge Case Handling (see below) is triggered if fewer than 5 ETFs remain after all filters
- **Prefer ETFs:** Grants all ETF funds a flat +5 bonus. In a universe where ETFs and active funds have similar quality scores, this typically shifts 1–2 ranking positions in favour of ETFs
- **No preference:** No action

### Regional Focus Logic Detail

Regional preferences are treated as portfolio tilts, not strict filters:
- Matching funds receive **+3 pts per matching region**
- In the allocation phase, matching funds receive a **proportionally higher weight** within the 5-fund portfolio
- If regional preferences would result in all 5 funds from the same region, the **diversification constraint (max 2 from same sub-category) takes precedence** and enforces geographic diversification

### Thematic Focus — Satellite Logic

Thematic funds are treated as satellite positions within the portfolio:
- At least 1 thematic fund is included if thematic preferences exist and a suitable fund is available
- Thematic funds receive a scoring bonus of **+3 pts**
- During portfolio construction, **10–20 % of portfolio weight** is reserved for thematic satellite positions
- Thematic funds typically exhibit higher volatility; allocation weight is risk-adjusted accordingly

---

## Edge Case Handling

### 1 — Too Few Funds After Filtering

**Trigger:** Fewer than 5 funds remain after all hard filters.

- **Resolution step 1:** Relax the risk profile filter bounds by **±1 SRRI level** and **±5 % on volatility and equity share thresholds**
- **Resolution step 2:** If still fewer than 5 funds, notify with warning: *"Restricted universe detected. The portfolio may contain funds at the edge of the suitability range."*
- **Resolution step 3:** If fewer than 3 funds remain after relaxation, request a preference review before proceeding

### 2 — ETF-Only Universe Too Restrictive

**Trigger:** "ETFs only" selected but fewer than 5 ETFs satisfy the risk and ESG filters.

- **Resolution:** Notify: *"Only N ETFs are available within your risk and sustainability criteria. Remaining positions will be filled with actively managed funds that broadly match your criteria."*
- **Behaviour:** Remaining positions drawn from the active fund ranking, clearly labelled as *"active fund (ETF not available)"* in the explainability output

### 3 — Strong Regional Preference Limits Diversification

**Trigger:** User selects a single narrow region (e.g. emerging markets only) and the risk profile is "Defensive" — few suitable bond funds for that region exist.

- **Resolution:** Treat regional preference as orientation, not mandate. Display warning: *"Full regional concentration in emerging markets is not compatible with a defensive risk profile. The portfolio will include global diversification."*
- **Behaviour:** Maximum **3 of 5 funds** may match the preferred region; the remaining 2 positions ensure geographic diversification

### 4 — Thematic Preferences Increase Portfolio Risk

**Trigger:** Selected themes (e.g. Technology) have high average volatility; including a thematic satellite would exceed the MDD tolerance of the risk profile.

- **Resolution:** Reduce satellite weight to the minimum (5 %), or exclude the satellite entirely if even 5 % would exceed the portfolio's total volatility target
- **Communication:** *"Your preferred theme (Technology) is available as a small satellite position of 5 %. A higher allocation would exceed the limits of your risk profile."*

### 5 — Conflicting Preferences

**Trigger:** ESG required + ETFs only + single region + theme — the intersection may be nearly empty.

**Resolution — apply preference hierarchy:**

1. ESG is **non-negotiable** if required by IDD
2. Risk profile is **non-negotiable**
3. ETF preference is relaxed **first**
4. Regional preference is relaxed **second**
5. Thematic preference is relaxed **third**

**Communication:** Show which preference was relaxed and why.

---

## Data Requirements

The following fund-level fields are required to implement this logic:

| Field | Used In | Required |
|-------|---------|----------|
| `srri` | Risk profile filter, scoring | Yes |
| `volatility` (annual %) | Risk profile filter, inverse vol weighting | Yes |
| `max_drawdown` | Risk profile filter, scoring | Yes |
| `yearly_fee` / `ter` | Scoring (cost efficiency) | Yes |
| `sharpe_ratio` | Scoring (risk-adjusted return) | Yes |
| `is_etf` | ETF preference filter | Yes |
| `esg_label` / `esg_article_8` / `esg_article_9` | ESG filter & bonus | Yes |
| `region` | Regional preference matching | Yes |
| `theme` | Thematic preference matching | Yes |
| `asset_class` | Core/Satellite classification, diversification cap | Yes |
| `provider` | Diversification cap (max 1 per provider) | Yes |
| `approved_for_germany` | Regulatory filter | Yes (or implicit via DB curation) |
| `is_active` (not in wind-down) | Regulatory filter | Yes (or implicit via DB curation) |

---

## Key Differences vs. Current Implementation

The following are notable changes relative to the current `decision_engine.py` logic:

| Aspect | Current | This Spec |
|--------|---------|-----------|
| Scoring weights | 40 % Sharpe / 30 % risk alignment / 30 % TER | **50 % Sharpe / 30 % MDD / 20 % TER** |
| MDD as scoring input | Not used (uses SRRI proximity for risk alignment) | **MDD is explicit scoring component** |
| Normalisation | 0–100 normalised directly | **Min-max per metric to 0–10, then weighted sum** |
| ESG soft bonus | +3 / +1.5 pts | **+5 pts** |
| ETF soft bonus | +5 pts | +5 pts (same) |
| Region/theme bonus | +3 pts each | +3 pts each (same) |
| Portfolio structure | Equal-weight start with risk-profile tilts | **Core-Satellite with inverse volatility weighting** |
| Core/Satellite classification | Not explicit | **Explicit Core (2–4) / Satellite (0–3) classification** |
| Weight bounds | Min 5 % / Max 35 % per fund | **Tiered bounds by position rank** |
| Diversification cap | Max 2 per asset class / max 2 per provider | **Max 2 per sub-category / max 1 per provider** |
| Regional allocation bonus | +0.02 weight tilt | **+20 % relative weight increase (× 1.2)** |
| Edge case: conflicting preferences | Single relaxation (widen risk band) | **Explicit preference hierarchy (5 levels)** |
| Edge case: ETF-only insufficient | Not explicitly handled | **Fallback to active funds with labelling** |
| Edge case: regional concentration | Not explicitly handled | **Hard cap: max 3/5 from preferred region** |
| Thematic satellite cap | Not explicit | **Portfolio weight cap: max 30 % total satellite** |
