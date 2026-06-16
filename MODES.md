# Multi-Mode UI — Contracts & Architecture

**Status:** Phase 0/1 — contract defined, shared result component extracted.

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
| `user_answers` | echo of the submitted answers |

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

---

## 4. Flow definitions (planned, Phase 3+)

Flow step grouping/ordering lives in **separate declarative configs** (e.g.
`flows/variantA.json`) that reference questionnaire section IDs — decoupled from
`preferences_schema.json` so A/B reordering needs no schema changes. The wizard
accumulates answers in the frontend and issues **one** `POST /api/portfolio`
at the final step (identical call to Quick-Mode).
