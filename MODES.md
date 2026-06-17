# Multi-Mode UI — Contracts & Architecture

**Status:** Phase 4 — contract defined; shared result component + mode handling
(`?mode=`) live. Two flow variants: A (`flows/variantA.json`, linear reference)
and B (`flows/variantB.json`, dummy-faithful with conditional navigation —
Komfort skip + region/theme Ja/Nein gates). Switch via `?flowVariant=A|B`.
Commercial fields are collected/persisted but ignored by the engine.

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
| `decision_trace.filters[]` | **technical trace:** filter steps `{name, before, after}` |
| `decision_trace.relaxations[]` | **technical trace:** relaxed constraints `{name, before, after, reason}` |
| `decision_trace.ranking` | **technical trace:** `{formula, top_k, candidates[]}` — the top_k scored pool with per-candidate breakdown (`base`, `sharpe_norm`, `mdd_norm`, `ter_norm`, `boosts`, `final`) and selection `status` (selected / skipped_provider_cap / skipped_category_cap / dropped_thematic / dropped_regional_cap / not_reached) |
| `decision_trace.selection` | **technical trace:** `{caps, events[]}` — diversification caps and selection adjustments (provider/category-cap skips, caps_relaxed, thematic_insert, regional_cap_drop/fill, etf_fallback_fill) |
| `decision_trace.allocation` | **technical trace:** `{satellite_cap_applied, funds[]}` — per-fund weighting: `class` (core/satellite), `inv_vol_raw`, `tier_bounds`, `after_clip`, `regional_tilt`, `final_weight` |
| `user_answers` | echo of the submitted answers |

The `ranking`/`selection`/`allocation` stages are **recording only** — the
engine computes them as a by-product of the existing pipeline and they never
influence the recommendation. Quick-Mode renders them in the Preferences tab;
Flow-Mode (`showTraces: false`) hides them.

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
- `showTraces: false` → Flow-Mode (end-user friendly). Hides the technical
  trace block. Summary and "Your Answers" recap stay visible in both modes.

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
| `/?mode=flow&flowVariant=A\|B` | A/B flow variants |

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
`"showIf": { "field": "<id>", "equals"|"notEquals": "<value>" }` or
`"showIf": { "allOf": [ <conditions> ] }`. Steps whose condition fails are
skipped during next/back navigation and excluded from the progress count;
answers owned by hidden steps are not sent in the final POST. Variant B uses
this for the Komfort skip (`aktivitaet notEquals "Komfort-Kunde"`) and the
region/theme Ja/Nein gates (`set_region`/`set_themes equals "ja"`).

`showIf` also works at the **field level** inside an inline `fields` step: a
field with an unmet condition is hidden while the step itself stays visible.
The contribution step uses this so only the relevant amount field shows per
payment mode (`beitragLaufend` when `beitrag notEquals "einmalig"`,
`beitragEinmalig` when `beitrag notEquals "laufend"`). The Next/"Generate"
button label is re-evaluated live as selections change, since the deciding
answer (e.g. Komfort vs. Aktiv) is made on the very step that governs it.

**Adding a variant:** drop a new `flows/variant<X>.json` and open
`?mode=flow&flowVariant=<X>` — no code change.
