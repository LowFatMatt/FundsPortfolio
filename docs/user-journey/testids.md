# `data-testid` Contract — Mein Fondskompass UI

> **State of the code:** [`static/js/app.js`](../../static/js/app.js) and [`templates/index.html`](../../templates/index.html) currently emit **zero** `data-testid` attributes (verified by search). The inventory below is therefore a **specification contract**, not a description of the DOM. Attach these ids while porting each screen from [`screens.md`](screens.md); the `Status` column tells you whether the screen's DOM already exists (attribute TODO only) or is still to be built.

## Convention

```
{screen}--{role}[-{name}]
```

- `{screen}` — canonical screen slug from the [coverage matrix](README.md#coverage-matrix) (`investment-objective`, `regions`, …). Lowercase, hyphenated.
- `{role}` — element role from the [vocabulary](#role-vocabulary) below.
- `{name}` — optional disambiguator, always the **option `value`**, **field id**, or **stable business key** (e.g. ISIN, period id), never the localized label. Normalization: lowercase, spaces/`/`/`&` → `-`, `_` kept as-is (schema values like `emerging_markets` stay verbatim).
- Separator is exactly two hyphens `--` between screen and role, one hyphen between role and name.
- Ids are **language-invariant** (labels translate, testids never do) and **layout-invariant** (a card, chip, or row keeps its id regardless of `display_hint`).
- Popups/menus attach under their owning screen (`{screen}--popup`, `{screen}--popup-confirm`, …) — popups are not separate screens.
- Dynamic rows (`result--fund-{ISIN}`) instantiate per item with the stable key; the pattern itself is part of the contract.
- `data-testid` never replaces semantics: elements must still carry proper tag/`name`/`aria-*` attributes. Tests target testids only.

## Role vocabulary

| Role | Element |
|------|---------|
| `root` | top-level container of one screen (one per screen) |
| `title` / `description` | heading / explanatory text |
| `option` | selectable choice; `name` = option value |
| `input` | form control; `name` = field id |
| `continue` / `back` | primary navigation (Weiter / Zurück) |
| `submit` | terminal action (save, load) |
| `btn` | non-navigation action button (`btn-ag`, `btn-details`) |
| `info` | mouseover/popover trigger; `name` = option value or key |
| `note` | inline gating/limit hint (`note-max`, `note-budget`) |
| `badge` | status marker (`badge-recommendation`) |
| `popup` (+ `-title` `-body` `-confirm` `-cancel` `-advisor` `-back`) | modal dialog and its controls |
| `row` | summary/key-value line; `name` = field id |
| `tab` / `chart` / `metric` / `count` | result-surface elements; `name` = key |
| `fund` | result fund row; `name` = ISIN; sub-controls append `-expand`, `-menu`, `-exchange`, `-remove` |
| `progress` / `error` / `session-banner` / `lang-select` / `restart` | persistent chrome (`screen` = `flow` or `chrome`) |

## Inventory

Status legend: **IMPLEMENTED-TODO** — screen exists in the prototype today; add the attribute to existing DOM. **SPEC** — screen is PLANNED; ids land with the build (see [README matrix](README.md#coverage-matrix)).

### Welcome & load

| testid | Screen | Status |
|--------|--------|--------|
| `welcome--root` / `welcome--title` | S-01 | IMPLEMENTED-TODO (`welcome-view`) |
| `welcome--start` / `welcome--load` | S-01 | IMPLEMENTED-TODO (start-fresh / resume actions) |
| `welcome--contact` / `welcome--advice` / `welcome--feedback` | S-01 | SPEC (links absent) |
| `portfolio-load--root` | S-02 | IMPLEMENTED-TODO (`resume-form`) |
| `portfolio-load--input-id` / `portfolio-load--submit` | S-02 | IMPLEMENTED-TODO (`resume-id`) |
| `portfolio-load--error` | S-02 | IMPLEMENTED-TODO (`resume-error`) |

### Commercial head (Endkunden web only)

| testid | Screen | Status |
|--------|--------|--------|
| `investment-objective--root` / `--title` | S-03 | IMPLEMENTED-TODO (flow step `goal`) |
| `investment-objective--option-altersvorsorge` | S-03 | IMPLEMENTED-TODO |
| `investment-objective--option-vermoegensaufbau` | S-03 | IMPLEMENTED-TODO |
| `investment-objective--option-kapitalanlage` | S-03 | IMPLEMENTED-TODO (no branch yet) |
| `investment-objective--continue` / `--back` | S-03 | IMPLEMENTED-TODO (flow nav) |
| `payment-types--root` / `--title` | S-04 | IMPLEMENTED-TODO (step `payment`) |
| `payment-types--option-laufend` / `--option-einmalig` / `--option-beides` | S-04 | IMPLEMENTED-TODO |
| `payment-types--continue` / `--back` | S-04 | IMPLEMENTED-TODO |
| `payments--root` | S-05 | IMPLEMENTED-TODO (step `contribution`) |
| `payments--input-beitrag_laufend` / `payments--input-beitrag_einmalig` | S-05 | IMPLEMENTED-TODO (fields `beitragLaufend`/`beitragEinmalig`) |
| `payments--input-laufzeit` | S-05 | SPEC ([D-09](README.md#d-09)) |
| `payments--info-beitrag_laufend` / `--info-beitrag_einmalig` | S-05 | SPEC (min/max mouseovers) |
| `payments--continue` / `--back` | S-05 | IMPLEMENTED-TODO |
| `product-selection--root` / `--title` | S-06 | IMPLEMENTED-TODO (step `product`) |
| `product-selection--option-fondsrente_vario` / `--option-garantrente_vario` | S-06 | IMPLEMENTED-TODO |
| `product-selection--btn-ag` | S-06 | SPEC |
| `product-selection--info-fondsrente_vario` / `--info-garantrente_vario` / `--info-ag` | S-06 | SPEC (Produktinformationsblatt/A&G popovers) |
| `product-selection--badge-recommendation` | S-06 | SPEC (recommendation mode) |
| `product-selection--continue` / `--back` | S-06 | IMPLEMENTED-TODO |

### A&G block

| testid | Screen | Status |
|--------|--------|--------|
| `ag-investment--root` | S-07 | SPEC |
| `ag-investment--option-goal-{value}` × 4 | S-07 | SPEC |
| `ag-investment--option-horizon-{value}` × 3 | S-07 | SPEC |
| `ag-investment--option-income-{value}` × 5 | S-07 | SPEC |
| `ag-investment--popup` / `--popup-confirm` / `--popup-cancel` | S-07 | SPEC (Vermögensübertrag wrong-journey popup) |
| `ag-investment--continue` / `--back` | S-07 | SPEC |
| `ag-knowledge--root` | S-08 | SPEC |
| `ag-knowledge--option-{value}` × 4 (product classes) | S-08 | SPEC |
| `ag-knowledge--option-ja` / `--option-nein` | S-08 | SPEC |
| `ag-knowledge--popup` / `--popup-advisor` / `--popup-back` | S-08 | SPEC (no-knowledge popup) |
| `ag-knowledge--continue` / `--back` | S-08 | SPEC |
| `ag-risk--root` | S-09 | SPEC |
| `ag-risk--option-behaviour-1` … `-4` | S-09 | SPEC |
| `ag-risk--option-loss-1` / `-2` | S-09 | SPEC |
| `ag-risk--continue` / `--back` | S-09 | SPEC |
| `product-recommendation--root` | S-10 | SPEC |
| `product-recommendation--option-fondsrente_vario` / `--option-garantrente_vario` | S-10 | SPEC |
| `product-recommendation--badge-fondsrente_vario` / `--badge-garantrente_vario` | S-10 | SPEC |
| `product-recommendation--continue` / `--back` | S-10 | SPEC |

### Strategy, ESG, ETF

| testid | Screen | Status |
|--------|--------|--------|
| `investment-strategy--root` / `--title` | S-11 | IMPLEMENTED-TODO (step `risk`) |
| `investment-strategy--option-conservative` / `--option-moderate` / `--option-aggressive` | S-11 | IMPLEMENTED-TODO |
| `investment-strategy--badge-recommendation` | S-11 | SPEC |
| `investment-strategy--info-conservative` / `--info-moderate` / `--info-aggressive` | S-11 | SPEC (vol 8/15/30 % mouseovers) |
| `investment-strategy--continue` / `--back` | S-11 | IMPLEMENTED-TODO |
| `esg-basic--root` / `--title` | S-12 | IMPLEMENTED-TODO (step `esg`) |
| `esg-basic--option-NONE` / `--option-ART_8_9_ONLY` / `--option-PREFER_ESG` | S-12 | IMPLEMENTED-TODO |
| `esg-basic--btn-details` | S-12 | SPEC |
| `esg-basic--info-{NONE\|ART_8_9_ONLY\|PREFER_ESG\|details}` | S-12 | SPEC |
| `esg-basic--popup` / `--popup-confirm` / `--popup-cancel` | S-12 | SPEC (slide-16 warning) |
| `esg-basic--continue` / `--back` | S-12 | IMPLEMENTED-TODO |
| `esg-details--root` | S-13 | SPEC |
| `esg-details--option-forms-ja` / `--option-forms-nein` | S-13 | SPEC |
| `esg-details--option-{value}` × 5 (characteristics) | S-13 | SPEC |
| `esg-details--popup` / `--popup-advisor` / `--popup-back` | S-13 | SPEC (universe-collapsed popup) |
| `esg-details--continue` / `--back` | S-13 | SPEC |
| `etf--root` / `--title` | S-14 | IMPLEMENTED-TODO (step `etf`) |
| `etf--option-no_preference` / `--option-prefer_etf` / `--option-etf_only` | S-14 | IMPLEMENTED-TODO |
| `etf--info-no_preference` / `--info-prefer_etf` / `--info-etf_only` | S-14 | SPEC |
| `etf--continue` / `--back` | S-14 | IMPLEMENTED-TODO |

### Personalization

| testid | Screen | Status |
|--------|--------|--------|
| `customer-type--root` / `--title` | S-15 | IMPLEMENTED-TODO (step `activity`) |
| `customer-type--option-komfort` / `--option-aktiv` | S-15 | IMPLEMENTED-TODO |
| `customer-type--info-komfort` / `--info-aktiv` | S-15 | SPEC (Aktiv text missing in spec, Q-3) |
| `customer-type--continue` / `--back` | S-15 | IMPLEMENTED-TODO |
| `region-gate--root` / `--title` | S-16 | IMPLEMENTED-TODO in variant B (step `region_gate`); SPEC for variant A |
| `region-gate--option-ja` / `--option-nein` | S-16 | IMPLEMENTED-TODO (B) |
| `region-gate--info-ja` / `--info-nein` | S-16 | SPEC |
| `region-gate--continue` / `--back` | S-16 | IMPLEMENTED-TODO (B) |
| `regions--root` / `--title` | S-17 | IMPLEMENTED-TODO (step `regions`) |
| `regions--option-germany` / `--option-europe` / `--option-north_america` | S-17 | IMPLEMENTED-TODO |
| `regions--option-asia` / `--option-emerging_markets` | S-17 | IMPLEMENTED-TODO (DEF hard-disable pending [D-05](README.md#d-05)) |
| `regions--option-{value}-disabled-reason` | S-17 | SPEC |
| `regions--note-max` / `--note-budget` | S-17 | budget note IMPLEMENTED-TODO; wording per [D-01](README.md#d-01) pending |
| `regions--continue` / `--back` | S-17 | IMPLEMENTED-TODO |
| `theme-gate--root` / `--title` | S-18 | IMPLEMENTED-TODO in variant B (step `themes_gate`); SPEC for variant A |
| `theme-gate--option-ja` / `--option-nein` | S-18 | IMPLEMENTED-TODO (B) |
| `theme-gate--info-ja` / `--info-nein` | S-18 | SPEC |
| `theme-gate--continue` / `--back` | S-18 | IMPLEMENTED-TODO (B) |
| `themes--root` / `--title` | S-19 | IMPLEMENTED-TODO (step `themes`) |
| `themes--option-commodities` / `--option-sustainability` / `--option-megatrends` / `--option-healthcare` / `--option-infrastructure` / `--option-ai_robotics` / `--option-defense` / `--option-water` / `--option-technology` / `--option-dividends` | S-19 | IMPLEMENTED-TODO (names per [D-07](README.md#d-07)) |
| `themes--info-{value}` × 10 | S-19 | SPEC |
| `themes--note-max` / `--note-budget` | S-19 | budget note IMPLEMENTED-TODO; DEF 0-theme rule pending [D-02](README.md#d-02) |
| `themes--continue` / `--back` | S-19 | IMPLEMENTED-TODO |

### Result surface

| testid | Screen | Status |
|--------|--------|--------|
| `result--root` / `result--count` | S-20 | IMPLEMENTED-TODO (`results-view`, `fund-count`) |
| `result--tab-summary` / `--tab-preferences` / `--tab-performance` / `--tab-volatility` | S-20 | IMPLEMENTED-TODO (4 tabs; 5th *Stresstest-Ergebnis* tab pending [D-14](README.md#d-14) notes) |
| `result--tab-stress` | S-20 | SPEC |
| `result--fund-{ISIN}` | S-20 | IMPLEMENTED-TODO (`fund-table-body` rows) |
| `result--fund-{ISIN}-expand` | S-20 | IMPLEMENTED-TODO (`.fund-expand-btn`) |
| `result--fund-{ISIN}-menu` / `-exchange` / `-remove` | S-20 | SPEC ([D-14](README.md#d-14)) |
| `result--metric-rendite` / `--metric-volatilitaet` | S-20 | IMPLEMENTED-TODO |
| `result--chart-asset-classes` / `--chart-regions` | S-20 | IMPLEMENTED-TODO (legends exist); themes breakdown SPEC |
| `preferences-summary--root` | S-21 | IMPLEMENTED-TODO (Preferences tab) |
| `preferences-summary--row-{field}` × 10 | S-21 | IMPLEMENTED-TODO; `row-investmentstrategie` SPEC |
| `performance--root` / `--metric-rendite` / `--metric-inflation` / `--metric-costs` | S-22 | PARTIAL → metric ids SPEC where values missing |
| `performance--period-{3y\|5y\|10y}` | S-22 | IMPLEMENTED-TODO for 3y/5y/10y (prototype adds 1y/si — keep or drop per spec) |
| `stress-test--root` | S-23 | IMPLEMENTED-TODO (stress overlay) |
| `stress-test--scenario-{id}` | S-23 | IMPLEMENTED-TODO (`data/stress_periods.json` toggles; COVID-19/INFLATION presets) |
| `save--root` / `save--submit` / `save--id-display` | S-24 | IMPLEMENTED-TODO (UUID persistence, `display-port-id`) |
| `save--download-pdf` / `save--upload-status` | S-24 | SPEC ([D-15](README.md#d-15)) |

### Branch (Kapitalanlage / GenDep / StarterKids) — all SPEC

| testid | Screen |
|--------|--------|
| `objective-capital-growth--option-vererben` / `--option-optimiert` (+ `--root` `--continue` `--back`) | S-26 |
| `product-selection-gendep--option-generationen_depot` / `--option-starter_kids` (+ `--root` `--continue` `--back`) | S-26 |
| `death-protection--root` / `--title` / `--option-ja` / `--option-nein` / `--continue` / `--back` | S-25 |
| `payments--input-sparrate` (25–200 €) / `payments--input-einmalbeitrag_sk` (250–999.999 €) | S-26 |

### Chrome

| testid | Status |
|--------|--------|
| `flow--progress` | IMPLEMENTED-TODO (`flow-progress-fill` / `-label`) |
| `flow--back` / `flow--continue` | IMPLEMENTED-TODO (`flow-back-btn` / `flow-next-btn`; continue becomes submit on last step) |
| `chrome--lang-select` | IMPLEMENTED-TODO (`lang-select`) |
| `chrome--session-banner` | IMPLEMENTED-TODO (`active-session-banner`) |
| `chrome--error` | IMPLEMENTED-TODO (`error-view` / `error-message`) |
| `chrome--restart` | IMPLEMENTED-TODO (`restart-btn`) |

## Implementation rules

1. **Add, don't replace** — existing ids/classes stay untouched; testids are additive metadata.
2. One testid per element; one `--root` per rendered screen; popups render inside their screen root.
3. Testids are emitted where the element is **created**: flow-step markup in [`app.js`](../../static/js/app.js) renderers, static chrome in [`templates/index.html`](../../templates/index.html).
4. When a step is re-used across flow variants (`region_gate` only in B), the testid is identical in both — presence differs, naming must not.
5. New options require only a `{value}`-suffixed entry — no code-side registry; this file is the registry and must be updated in the same PR that adds an option.
