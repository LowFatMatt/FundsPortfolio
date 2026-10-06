# Multi-Mode UI — Contracts & Architecture

**Status:** Phase 4 — contract defined; shared result component + mode handling
(`?mode=`) live. Three flow variants: A (`flows/variantA.json`, linear reference),
B (`flows/variantB.json`, dummy-faithful with conditional navigation —
Komfort skip + region/theme Ja/Nein gates) and C (`flows/variantC.json`,
**phase model** — product-determination phase skipped one-way under a
`?product=` handover, no Komfort/Aktiv persona). Switch via
`?flowVariant=A|B|C`. Commercial fields are collected/persisted but ignored by
the engine.

This document is the binding contract for the multi-mode prototype (Quick-Mode,
Flow-Mode, future A/B flow variants). All modes share **one logic core, one REST
API, and one result-rendering component**. Modes differ only in *how inputs are
collected* and *how much trace detail is shown* — never in the API they call.

---

## 1. Logic API contract (unchanged across all modes)

Single entry point for the decision logic:

```
POST /api/portfolio
Content-Type: application/json

{
  "user_answers": { "<section_id>": "<value>" | ["<value>", ...], ... },
  "language":     "de" | "en",          // optional; falls back to Accept-Language
  "portfolio_id": "port_..."            // optional; present when editing/resuming
}
```

**Response (201):** a portfolio object. The result component depends only on
these fields:

| Field | Meaning |
|-------|---------|
| `portfolio_id` | persisted ID (14-day resume window) |
| `risk_profile` | resolved risk profile label |
| `recommendations[]` | selected funds (name, isin, allocation_percent, quality_score, asset_class, fee, explanations, breakdowns) |
| `portfolio_metrics` | aggregate metrics (e.g. `weighted_fee`) |
| `explanations.summary` | user-facing decision summary |
| `decision_trace.filters[]` | **technical trace:** filter steps `{name, before, after}` — incl. layer-0 `product_context` (`details.product` = canonical key or `null`) |
| `decision_trace.relaxations[]` | **technical trace:** relaxed constraints `{name, before, after, reason}` |
| `decision_trace.ranking` | **technical trace:** `{formula, top_k, candidates[]}` — the top_k scored pool with per-candidate breakdown (`base`, `sharpe_norm`, `mdd_norm`, `ter_norm`, `boosts`, `final`) and selection `status` (selected / skipped_provider_cap / skipped_category_cap / dropped_thematic / dropped_regional_cap / not_reached) |
| `decision_trace.selection` | **technical trace:** `{caps, events[]}` — diversification caps and selection adjustments (provider/category-cap skips, caps_relaxed, thematic_insert, regional_cap_drop/fill, etf_fallback_fill) |
| `decision_trace.allocation` | **technical trace:** `{satellite_cap_applied, funds[]}` — per-fund weighting: `class` (core/satellite), `inv_vol_raw`, `tier_bounds`, `after_clip`, `regional_tilt`, `final_weight` |
| `user_answers` | echo of the submitted answers (incl. `product_context` when a `product` was supplied) |

The `ranking`/`selection`/`allocation` stages are **recording only** — the
engine computes them as a by-product of the existing pipeline and they never
influence the recommendation. Both modes render them in the Preferences tab
(product feedback 2026-10-05: the trace is wanted in Flow-Mode too; the
`showTraces` flag remains as the shared component's switch).

**Partial input:** `ql.apply_defaults()` already injects defaults for missing
logic-relevant answers, so the endpoint tolerates incomplete `user_answers`
today. This is the hook for **Variant 3** (incremental logic) later — the
contract does not need to change to support partial computation.

---

## 2. Result-view contract (shared component)

Every mode renders results through one entry point in `static/js/app.js`:

```js
renderResults(portfolio, { showTraces = true } = {})
```

- `showTraces: true`  → Quick-Mode. Renders the technical decision trace
  (`#decision-filters` = `decision_trace.filters` + `relaxations`).
- `showTraces: false` → hides the technical trace block. Summary and
  "Your Answers" recap stay visible in either case. Flow-Mode passes
  `showTraces: true` since 2026-10-05 (the wizard's result presentation needs
  the trace for transparency).

The component reads only the response fields listed in §1. It owns the
Summary / Preferences / Performance / Volatility tabs and is mode-agnostic
beyond the `showTraces` flag.

---

## 3. Mode handling (planned, Phase 2+)

One SPA, selected via query parameter (default = `flow`):

| URL | Mode |
|-----|------|
| `/` or `/?mode=flow` | Flow-Mode (multi-step wizard) — **default** |
| `/?mode=quick` | Quick-Mode (single-page form + full traces) |
| `/?mode=flow&flowVariant=A\|B\|C` | A/B/C flow variants |

Branding (`brand/`) and i18n (`static/i18n/`) are already centralized and apply
to every mode automatically — no per-mode duplication.

### Why two axes (`mode` + `flowVariant`) instead of `mode=flowA`

`mode` (Quick vs. Flow) and `flowVariant` (which flow layout) vary
**independently**: a variant change stays within Flow, and Quick has no variant
at all. Two independent dimensions → two parameters. Keeping them separate means
a new variant is just a new `flows/X.json` (data lookup, zero code change),
branching stays simple (`if (mode === 'flow')` instead of `flowA || flowB || …`),
and the axes can be combined freely later.

### Resuming a portfolio across modes

A portfolio's `user_answers` carries whatever the originating mode collected —
for Flow-Mode that includes the commercial extras (`anlageziel`, `beitrag`,
`produkt`, …). When you **resume** such a portfolio in **Quick-Mode** and
regenerate, only the five logic sections are re-collected (the Quick form has no
inputs for the commercial fields), so the extras are dropped from the new
portfolio. This is expected and intentional: the recommendation is identical
(the engine never used those fields), and it doubles as a handy way to **strip a
portfolio down to its logic-relevant inputs**. Resume currently always opens the
Quick form, even in Flow-Mode; prefilling the wizard is a later enhancement.

### Why Quick is its own mode, not a one-step flow

Quick *could* be modelled as a degenerate single-step flow, and that is the more
elegant end-state. We keep it separate for now because: (1) Quick is the trusted
**reference oracle** for the Phase 6 "Quick == Flow for equal inputs" test — it
must not run through the same wizard code it validates; (2) Quick is a stable
internal testing/explanation tool that should not be entangled with A/B
experimentation on the Flow surface; (3) it preserves the working status quo
while the wizard is built. The expensive parts (field renderers, `renderResults`)
are already shared, so unifying would save little. **Reversible:** once the
wizard is proven, Quick can be re-expressed as `flows/quick.json` (one step, all
sections, `showTraces: true`) and the separate path retired.

---

## 4. Flow definitions

Flow step grouping/ordering lives in **separate declarative configs**
(`flows/variant<X>.json`, served at `/flows/...`) — decoupled from
`preferences_schema.json` so A/B reordering needs no schema changes. The wizard
accumulates answers in the frontend and issues **one** `POST /api/portfolio`
at the final step (identical call to Quick-Mode).

**Step shape:**
- `{ "source": "section", "section": "<id>" }` — render a questionnaire section
  (localized by the API). Optional `display_hint` / `max` override its
  presentation in the flow only (e.g. render a `chips` section as `cards` with a
  selection cap), without touching the shared schema.
- `{ "source": "inline", "section": {…} }` or `{ "source": "inline", "fields": [{…}] }`
  — fields defined in the config itself (commercial steps, number inputs). Inline
  labels/descriptions are bilingual objects `{ "de": …, "en": … }`, resolved to
  the active language at render time. Field `type` supports `single_select`,
  `multi_select`, and `number` (with `min`/`step`/`value`/`suffix`).

**Conditional navigation** (`showIf`): any step may declare
`"showIf": { "field": "<id>", "equals"|"notEquals": "<value>" }`,
`"showIf": { "allOf": [ <conditions> ] }` (all must hold) or
`"showIf": { "anyOf": [ <conditions> ] }` (at least one must hold). Steps
whose condition fails are skipped during next/back navigation and excluded
from the progress count; answers owned by hidden steps are not sent in the
final POST. Variant B uses this for the Komfort skip
(`aktivitaet notEquals "Komfort-Kunde"`) and the region/theme Ja/Nein gates
(`set_region`/`set_themes equals "ja"`).

`showIf` also works at the **field level** inside an inline `fields` step: a
field with an unmet condition is hidden while the step itself stays visible.
The variant C payment step uses **positive `anyOf` reveal**: an amount field
appears only once its payment mode is explicitly chosen (monthly for
`laufend`/`beides`, one-off for `einmalig`/`beides`) — before any choice
neither field shows, matching the spec's *"Je nach Auswahl erscheint entweder
das eine und/oder das andere"*. When an interaction changes which sections of
the current step are visible, the wizard re-renders the step in place
(`applyPrefill` restores every answer). The Next/"Generate"/adaptive CTA
label is re-evaluated live as selections change.

**Feasibility gating metadata** (both modes, served with the questionnaire):
the questionnaire root carries a `preference_gating` block —
`{ budget: { fields: [...], max_by_profile: {DEFENSIVE: 1, BALANCED: 2,
OPPORTUNITY: 3}, per_field_max_by_profile: {BALANCED: {preferred_regions: 1,
preferred_themes: 1}} }, option_exclusions_by_profile: {DEFENSIVE:
{etf_preference: [etf_only]}, BALANCED: {etf_preference: [etf_only]}},
option_fallbacks: {etf_only: prefer_etf}, answer_to_profile: {...},
filters: [{field, value, combo_key}] }` — and every region/theme option
carries `feasible`: precomputed fund counts per (risk profile × `esg8_9` ×
`etf` filter combination). The SPA resolves the live combination from the
answers (risk/ESG/ETF questions precede regions/themes in every flow),
renders options with zero funds as **disabled-with-reason** (never hidden),
and caps combined region+theme selections at the profile budget. The
optional `option_exclusions_by_profile` block (L0, resolves user-journey
decision D-19) removes whole options from the answer space — `etf_only`
under DEFENSIVE/BALANCED (the ETF-only universe inside those bands is too
small for a diversified selection); excluded options also render
disabled-with-reason and stale values are downgraded to their
`option_fallbacks` target at submission boundaries. The optional
`per_field_max_by_profile` vector adds per-dimension composition caps
(BALANCED: max 1 region and max 1 theme — the only 2-selection composition
is 1R+1T; resolves user-journey decision D-03); the effective per-section
cap is `min(per-section max, remaining budget, per-field cap)`, so profiles
without a per-field entry keep the pure shared budget. Back-navigation
prunes now-infeasible and over-budget selections with a visible notice; the
flow submit drops infeasible and over-cap values defensively. Direct API
calls are never rejected — infeasible answers produce soft warnings in the
portfolio logs. Counts are derived from the live funds DB by
[`funds_portfolio/dialog/feasibility.py`](../funds_portfolio/dialog/feasibility.py),
which shares its band/filter semantics with the engine (no drift possible).

**Phase model (variant C)** — `flows/variantC.json` replaces the flat
`steps` list with declarative `phases` (plans/user-journey-redesign.md §1):

```json
{ "phases": [
  { "id": "product-determination", "title": {"de": "…", "en": "…"},
    "skipOnProductContext": true, "steps": [ …goal, payment, contribution, product… ] },
  { "id": "strategy-preferences",  "title": {"de": "…", "en": "…"},
    "steps": [ …risk, esg, etf, regions, themes… ] } ] }
```

The loader flattens phases into the same step list the engine already
navigates (each step tagged with its `phase` id), so every existing mechanism
(`showIf`, feasibility gating, progress) keeps working unchanged. Phase
semantics:

- **Entry-channel skip (D-10/D-21):** a phase with
  `skipOnProductContext: true` vanishes when the journey is entered with a
  valid `?product=` handover — the insurance product (and its fund universe)
  was determined upstream. **One-way:** Back-navigation from the first
  strategy step returns to the welcome screen, never into the skipped phase;
  restart re-enters the wizard directly (still past the skipped phase).
- **Auto-start:** with `?product=` or an explicit `#/<step-id>` hash, the
  wizard opens directly after the questionnaire loads (welcome screen
  bypassed). An invalid `?product=` surfaces the API error instead of
  starting the wizard. "Start Over" clears the step hash and re-enters at the
  FIRST visible step (with a `?product=` context directly in the wizard,
  otherwise on the welcome screen) — a stale hash must never act as a back
  button into the last visited step.
- **Session end:** generating the portfolio or backing out to welcome clears
  the `#/<step-id>` hash, so URLs shared from the results view stay clean.
- **Hash deep links:** `#/<step-id>` (e.g. `?product=avg80#/risk`) jumps
  straight to a visible step; the current step is mirrored back into the URL
  via `replaceState`; `hashchange` navigates between steps while the wizard
  is open. Deep links into a skipped phase resolve to "not visible" and fall
  back to the phase-B entry.
- **Answers:** hidden (skipped-phase) steps' keys are dropped from the final
  POST by the existing `mapFlowToUserAnswers` hidden-step rule.
- **Progress:** the phase indicator (`flow--phase-indicator`, one chip per
  phase with visible steps; active/done states) renders above the progress
  bar for phase-model variants; flat variants A/B keep the plain bar.
- **No persona:** variant C has no Komfort/Aktiv (`activity`) step and no
  region/theme Ja/Nein gates — every customer gets the preference steps
  (product decision 2026-10-05).
- **MVP-2 click reduction (per-step properties, variant C only):**
  `auto_advance: true` advances single-select card steps on selection
  (goal, product, risk; Flow-Mode only); `optional: true` marks skippable
  steps (regions/themes — "Optional" chip, empty selection is valid); an
  adaptive `cta` (`empty_label`/`filled_label`, `{de,en}`) relabels the
  always-enabled next button (`flow--cta`) live while selecting; steps can
  merge screens — `section` + `fields` on one step (payment mode + amounts)
  or `sections: [...]` stacking questionnaire sections (ESG + ETF as one
  preferences screen). The sticky `flow--feasible-count` footer shows
  `preference_gating.universe_totals` (funds per risk approach × ESG/ETF
  combo, product-reduced under a `?product=` handover) once the risk
  approach is answered.

**Adding a variant:** drop a new `flows/variant<X>.json` and open
`?mode=flow&flowVariant=<X>` — no code change. A config may use either the
phase model or a flat `steps` list; the contract tests in
[`tests/test_flow_variants.py`](tests/test_flow_variants.py) pin both shapes.
