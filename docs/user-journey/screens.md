# Screen Specifications — Mein Fondskompass

> **Companion to [`README.md`](README.md).** One spec block per canonical screen, in journey order.
> `data-testid` values are the **contract** defined in [`testids.md`](testids.md) — none exist in the DOM yet.
> German quotes are verbatim spec wording from `notes/pptx_klickstrecke_text.txt` (slide numbers) and the commented PDF; they are normative for behaviour, not for final copy.
> Screens S-01…S-24 follow the main flow; S-25/S-26 cover the Kapitalanlage branch.

Legend for interaction tables — **testid** omits the `data-testid` attribute name; **spec** states required behaviour incl. gating.

---

## S-01 · `welcome` — Willkommen im Fondskompass

| | |
|---|---|
| **Sources** | PPT 1–2 · PDF *"Willkommen im Mein Fondskompass!"* · prototype `welcome-view` |
| **Status** | PARTIAL |

- **Intent:** landing screen; explain value proposition (*"Gestalten Sie ihr ganz persönliches Anlageportfolio – einfach, flexibel und verständlich"*) and offer the three actions.
- **Entry:** application start (`/`).
- **Exit:** → `investment-objective` (start) or → `portfolio-load` (resume) or external (Kontakt/Beratung/Feedback).
- **Gating:** none. Always first.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `welcome--root` | container of all welcome elements |
| Headline | `welcome--title` | *"Willkommen im Fondskompass der Provinzial!"* |
| Start button | `welcome--start` | *"Jetzt starten"* → next screen |
| Resume button | `welcome--load` | *"Bestehendes Portfolio laden"* → `portfolio-load` |
| Contact link | `welcome--contact` | *"Kontakt"* — external, target TBD |
| Advice link | `welcome--advice` | *"Beratung"* — external, target TBD |
| Feedback link | `welcome--feedback` | *"Feedback"* — external, target TBD |

**Spec annotations (PPT 1–2):**
- *"Ab Start 4 Farbthemes benötigt (Provinzial Grün, Provinzial Blau, HFK Rot, Sparkassen Rot). Über URL geregelt…"* → [D-18](README.md#d-18), affects URL contract, not this screen's DOM.
- *"Datenübergabe von LeAn in den MFK für 2027 geplant und soll bereits vorbereitet und bedacht werden. Übergebene Daten: Produkt, Ergebnisse A&G (falls vorhanden), Maskendesign?"* → [D-10](README.md#d-10)/Q-4.
- notesSlide2 (consent, B2B2C vs. B2C): *"In B2B2C Strecke opt. Freitextfeld für Einwilligung / In B2C Strecke darf bei Nein nicht weiter gehen und keine Produkteignung ausgesprochen werden"* → unmapped, Q-8.
- **Prototype delta:** resume + start exist; Kontakt/Beratung/Feedback absent.

---

## S-02 · `portfolio-load` — Vorgang laden

| | |
|---|---|
| **Sources** | PDF *"Please insert your Portfolio ID"* / *"Portfolio could not be loaded"* / decision *"Portfolio found? no"* · PPT 1–2 (button only) · prototype `resume-form` |
| **Status** | IMPLEMENTED |

- **Intent:** re-open a previously saved Beispiel-Portfolio by ID.
- **Entry:** `welcome--load`.
- **Exit:** → `result` on success (PDF: portfolio content shown); back to `welcome` on failure.
- **Gating:** none.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `portfolio-load--root` | |
| ID input | `portfolio-load--input-id` | *"Please insert your Portfolio ID"* |
| Submit | `portfolio-load--submit` | validates + loads |
| Error message | `portfolio-load--error` | shown on failure: *"Portfolio could not be loaded"* |

**Prototype delta:** implemented as `resume-form`/`resume-id`/`resume-error`; loads by UUID. Testids to be attached.

---

## S-03 · `investment-objective` — Welches Anlageziel haben Sie?

| | |
|---|---|
| **Sources** | PDF `ID: InvestmentObjective` · PPT 3 (base), 30/34 (alt wording), 31/35 (Kapitalanlage variant) · flow step `goal` |
| **Status** | PARTIAL |

- **Intent:** segment the customer by goal; drives wording of subsequent screens and the Kapitalanlage branch.
- **Entry:** `welcome--start`.
- **Exit:** → `payment-types` for `altersvorsorge` / `vermoegensaufbau`; → `objective-capital-growth` for `kapitalanlage`.
- **Gating:** **Endkunden-web only** — skipped when entering from Tarifrechner/Online Sales (PPT 3: *"Seite nur in der Endkunden Webversion relevant…"*).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `investment-objective--root` | |
| Title | `investment-objective--title` | *"Welches Anlageziel haben Sie?"* |
| Option Altersvorsorge | `investment-objective--option-altersvorsorge` | card, single-select |
| Option Vermögensaufbau | `investment-objective--option-vermoegensaufbau` | card, single-select |
| Option Kapitalanlage | `investment-objective--option-kapitalanlage` | card, single-select → branches |
| Continue | `investment-objective--continue` | disabled until selection |
| Back | `investment-objective--back` | → `welcome` |

**Spec annotations:**
- PDF (on `payments`): `only "Altersvorsorge" or "Vermögensaufbau"` — the main path is restricted to these two goals; `Kapitalanlage` leaves it.
- PPT 3: *"Gleiche Strecke, unterschiedliches Wording um Kunden bedarfsgerecht und situativ anzusprechen"* — wording variants are intentional (30/34 restated, 31/35 replace cards with *Vererben/verschenken* + *Optimiert anlegen*).
- **Prototype delta:** 3 options only, no branch, no channel skip.

---

## S-04 · `payment-types` — Beitragszahlung

| | |
|---|---|
| **Sources** | PDF `ID: PaymentTypes` · PPT 4 · flow step `payment` |
| **Status** | IMPLEMENTED |

- **Intent:** choose contribution mode; gates the two amount fields on `payments`.
- **Entry:** `investment-objective`.
- **Exit:** → `payments`.
- **Gating:** Endkunden-web only (PPT 4 note).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `payment-types--root` | |
| Title | `payment-types--title` | *"Welche Beitragszahlung bevorzugen Sie?"* |
| Option laufend | `payment-types--option-laufend` | *"Die Beitragszahlung erfolgt laufend"* |
| Option einmalig | `payment-types--option-einmalig` | *"Die Beitragszahlung erfolgt einmalig"* |
| Option beides | `payment-types--option-beides` | *"Die Beitragszahlung erfolgt einmalig und laufend"* |
| Continue / Back | `payment-types--continue` / `payment-types--back` | continue disabled until selection |

**Prototype delta:** implemented (`payment` step, values `laufend`/`einmalig`/`beides`).

---

## S-05 · `payments` — Beiträge & Laufzeit

| | |
|---|---|
| **Sources** | PDF `ID: Payments` (used for this screen and its branch variants) · PPT 5 (main), 32/38 (branch one-off), 41 (StarterKids) · flow step `contribution` |
| **Status** | PARTIAL |

- **Intent:** capture amounts (and duration) with validated bounds.
- **Entry:** `payment-types`.
- **Exit:** → `product-selection`.
- **Gating:** Endkunden-web only (PPT 5). Field-level: monthly shown iff mode ≠ `einmalig`; one-off shown iff mode ≠ `laufend` (PPT 5: *"Je nach Auswahl erscheint entweder das eine und / oder das andere"*; prototype `showIf`).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `payments--root` | |
| Monthly input | `payments--input-beitrag_laufend` | slider/number, **min 25 €**, step 5, marker 600 € |
| One-off input | `payments--input-beitrag_einmalig` | slider/number, **min 1.000 €**, markers 5.000 / 200.000 / 1.000.000 € |
| Duration input | `payments--input-laufzeit` | slider **12 Jahre … 50 Jahre+**, default 30 — **not implemented** ([D-09](README.md#d-09)) |
| Continue / Back | `payments--continue` / `payments--back` | validation per mouseover rules below |

**Spec annotations (PPT 5):**
- Mouseover: *"Mindest- und Max Beitrag erklären … Einmalbeitrag min max erklären und alt. Handlungsanweisung ergänzen"* — bounds need explanatory popover incl. a recommended action when out of range.
- *"Hinweis Altershöchstgrenze und falls unter 12 Jahre"* — age-limit hint tied to the duration slider; rule text not yet supplied.
- Branch variants: PPT 32/38 one-off only with *"Min und max Werte aus Tarifrechner so vorgegeben"*; PPT 41 StarterKids: Sparrate min **25 €** (preselected) **max 200 €/Monat (2.400 jährlich)**, Einmalbeitrag **250–999.999 €** → [D-16](README.md#d-16).
- **Prototype delta:** two number inputs with min/step/default (`25/5/100`, `1000/500/10000`) + `showIf`; **no duration slider, no branch bounds**.

---

## S-06 · `product-selection` — Rentenversicherung FRV / GRV

| | |
|---|---|
| **Sources** | PDF `ID: PensionInsuranceVarioType` (+ `ID: PensionInsuranceProductSelection` for payload entry) · PPT 6/7 (variants), 33 (Tarifrechner join), 36/40 (GenDep/StarterKids cards) · flow step `product` |
| **Status** | PARTIAL |

- **Intent:** choose the pension wrapper; optionally launch A&G; or receive the product from the entry channel.
- **Entry:** `payments` (Endkunden) · direct (Tarifrechner — screen **skipped**, product via payload) · `objective-capital-growth` (branch variant).
- **Exit:** → `ag-investment` (A&G button) or → `investment-strategy` (Weiter; PDF Tarifrechner note: *"Ab hier Sprung in normale AV / VM Strecke mit next Step Risiko"*).
- **Gating:** Endkunden-web only when interactive.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `product-selection--root` | |
| Title | `product-selection--title` | *"Welche Rentenversicherung kommt für Sie in Frage?"* |
| Card FRV | `product-selection--option-fondsrente_vario` | 3 bullets each, wording per PPT 6/7 |
| Card GRV | `product-selection--option-garantrente_vario` | 3 bullets each |
| Recommendation badge | `product-selection--badge-recommendation` | present in recommendation mode ([D-11](README.md#d-11)) |
| A&G button | `product-selection--btn-ag` | *"Angemessenheits- & Geeignetheitsprüfung durchführen"* — Optional (PPT 7) |
| Info FRV | `product-selection--info-fondsrente_vario` | mouseover *"Produktinformationsblatt FRV"* (PPT 7) |
| Info GRV | `product-selection--info-garantrente_vario` | mouseover *"Produktinformationsblatt GRV"* (PPT 7) |
| Info A&G | `product-selection--info-ag` | mouseover *"Erklärungstext A&G"* (PPT 7) |
| Continue / Back | `product-selection--continue` / `product-selection--back` | |

**Spec annotations:**
- PDF: `show recommendation "for Angemessenheit- Geeignetheitsprüfung"` on the product screen — the A&G CTA is surfaced here (PPT 6 header block *"ANGEMESSENHEITS- & GEEIGNETHEITSPRÜFUNG Optional"*).
- PPT 7 GRV bullet differs from PPT 6: *"Festlegung einer individuellen Beitragsgarantie von 10 – 100 %"*. PPT 12 = same screen in recommendation mode (*"Empfehlung gemäß Mapping in A&G"*).
- *"Künftig noch ein weiteres Produkt denkbar (Vario Garant / Hybrid Produkt)"* (PPT 6/7) → Q-5.
- **Prototype delta:** two cards, no A&G button, no infos, no payload mode, no GenDep/StarterKids cards.

---

## S-07 · `ag-investment` — A&G · Fragen zu Ihrer Anlage

| | |
|---|---|
| **Sources** | PDF A&G block · PPT 8 | 
| **Status** | PLANNED |

- **Intent:** first A&G block — investment goal, horizon, disposable income (regulatory appropriateness).
- **Entry:** `product-selection--btn-ag`.
- **Exit:** → `ag-knowledge`.
- **Gating:** A&G block is optional and runs as a detour; results feed S-10/S-11.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `ag-investment--root` | header *"Angemessen- & Geeignetheitsprüfung"* |
| Q1 Anlageziel | `ag-investment--option-goal-{value}` | 4 options: *Sparen für besondere Wünsche (Vermögensaufbau) · Verbesserung meiner Rente (Altersvorsorge) · Eigene vier Wände (Immobilie) · Vermögensübertrag* |
| Q2 Anlagedauer | `ag-investment--option-horizon-{value}` | *Bis 12 Jahre · Über 12 Jahre · Über 20 Jahre* |
| Q3 Einkommen | `ag-investment--option-income-{value}` | *0 € bis 150 € · Bis 300 € · Bis 500 € · Über 500 € · Keine bzw. unvollständige Angabe* |
| Continue / Back | `ag-investment--continue` / `ag-investment--back` | |

**Spec annotations (PPT 8):**
- *"Bei vermögensübertrag empfiehlt der Tarifrechner das Generationendepot"* → if Q1 = Vermögensübertrag: **popup** *"aka falsche Strecke und Bestätigung ja nein und link zurück auf los"* (confirm leaving the journey; → [D-16](README.md#d-16)).

---

## S-08 · `ag-knowledge` — A&G · Kenntnisse & Erfahrungen

| | |
|---|---|
| **Sources** | PPT 9 |
| **Status** | PLANNED |

- **Intent:** knowledge & experience per product class (regulatory suitability).
- **Entry:** `ag-investment`.
- **Exit:** → `ag-risk` if knowledge = Ja; **error popup** if Nein.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `ag-knowledge--root` | |
| Known products multi-select | `ag-knowledge--option-{value}` | *Lebens- oder Rentenversicherungen · Investmentfonds (Aktien-, Renten- und Mischfonds) · Alternative Investments · Keine bzw. unvollständige Angaben* |
| Knowledge toggle | `ag-knowledge--option-ja` / `ag-knowledge--option-nein` | *"Ja, ich habe bereits Kenntnisse." / "Nein, ich habe keine Kenntnisse."* |
| Error popup | `ag-knowledge--popup` | see annotation |
| Popup CTA advisor | `ag-knowledge--popup-advisor` | *"Verweis auf Beratung über Berater in Agentur oder zurück"* |
| Popup cancel | `ag-knowledge--popup-back` | |
| Continue / Back | `ag-knowledge--continue` / `ag-knowledge--back` | continue requires knowledge ≠ Nein or popup resolution |

**Spec annotations (PPT 9):** *"Error Handling notwendig wenn Kunde keine Kenntnisse hat ODER Aufschlauen — Kein Aufschlauen, Pop Up mit Verweis auf Beratung…"* → decision Aufschlauen vs. block ([Q-6](README.md#open-spec-questions-verbatim-from-sources-unanswered)).

---

## S-09 · `ag-risk` — A&G · Fragen zu Ihrem Risikoverhalten

| | |
|---|---|
| **Sources** | PPT 10–11 |
| **Status** | PLANNED |

- **Intent:** two-dimensional risk assessment: risk behaviour (Q1, options 1–4) × loss capacity (Q2, options 1–2); result pair `x&y` feeds the mapping table.
- **Entry:** `ag-knowledge`.
- **Exit:** → `product-recommendation`.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `ag-risk--root` | |
| Q1 option 1–4 | `ag-risk--option-behaviour-{1..4}` | 1 *"…vor allen Dingen Sicherheit wichtig"* … 4 *"Für sehr hohe Renditechancen verzichte ich auf eine Beitragsgarantie…"* |
| Q2 option 1–2 | `ag-risk--option-loss-{1..2}` | 1 *"Ich brauche ein Produkt mit hohen Garantien…"* · 2 *"Finanziell bin ich in der Lage auch höhere Verluste zu tragen."* |
| Continue / Back | `ag-risk--continue` / `ag-risk--back` | both questions required |

**Spec annotations (PPT 11):** mapping `1&1…4&2 → Produkt + Risikoprofil` — full table in [D-11](README.md#d-11); note *"Empfehlung Risikoprofil Zurückhaltend für GRV im Kern unsinnig"* (Q-1).

---

## S-10 · `product-recommendation` — Empfehlung gemäß A&G

| | |
|---|---|
| **Sources** | PDF `ID: PensionInsuranceVarioTypeRecommendation` · PPT 12 |
| **Status** | PLANNED |

- **Intent:** re-present S-06 with the recommended product highlighted (*"Empfehlung gemäß Mapping in A&G"*); customer still chooses.
- **Entry:** `ag-risk`.
- **Exit:** → `investment-strategy` (with `InvestmentStrategyRecommendation`).
- **Gating:** only reached via A&G.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `product-recommendation--root` | |
| Recommended badge FRV/GRV | `product-recommendation--badge-{product}` | marks mapped product; alternative shown as *"Alt …"* when mapping lists two |
| Cards | `product-recommendation--option-{product}` | same cards as S-06 |
| Continue / Back | `product-recommendation--continue` / `product-recommendation--back` | |

---

## S-11 · `investment-strategy` — Anlagestrategie / Risikoneigung

| | |
|---|---|
| **Sources** | PDF `ID: InvestmentStrategy` + `ID: InvestmentStrategyRecommendation` · PPT 13, 39, 42 · flow step `risk` → section `risk_approach` |
| **Status** | PARTIAL |

- **Intent:** select the risk profile that bounds the fund universe (vol bands) and the preference budget.
- **Entry:** `product-selection` / `product-recommendation` (also re-entered after Back navigation from later screens).
- **Exit:** → `esg-basic` (main flow); in the StarterKids branch → `result` directly (*"Bei Klick auf Weiter wird das Portfolio direkt erstellt"*, PPT 39).
- **Gating:** PDF `show recommendation "for persönliche Risikopräferenz" AND it was not asked before` — if A&G already assessed risk, the recommendation is preselected/marked instead of re-asked. PPT 13: *"Optional, nur klickbar wenn Kunde vorne keine A&G macht. Dann nur Schritt Risiko."*

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `investment-strategy--root` | |
| Title | `investment-strategy--title` | *"Welche Anlagestrategie passt zu Ihrer persönlichen Risikoneigung?"* |
| Card Zurückhaltend | `investment-strategy--option-conservative` | value `conservative` → DEFENSIVE |
| Card Ausgewogen | `investment-strategy--option-moderate` | value `moderate` → BALANCED |
| Card Chancenorientiert | `investment-strategy--option-aggressive` | value `aggressive` → OPPORTUNITY |
| Recommendation badge | `investment-strategy--badge-recommendation` | from A&G mapping when present |
| Info Zurückhaltend | `investment-strategy--info-conservative` | mouseover *"Volatilität bis max. 8 % (5-Jahresdurchschnitt)"* |
| Info Ausgewogen | `investment-strategy--info-moderate` | mouseover *"Volatilität bis max. 15 % (5-Jahresdurchschnitt)"* |
| Info Chancenorientiert | `investment-strategy--info-aggressive` | mouseover *"Volatilität bis max. 30 %"* — note: **no `(5-Jahresdurchschnitt)` suffix** on slides 13/39 but present in notesSlide13/14 and slide 42 → engine divergence [D-06](README.md#d-06) |
| Continue / Back | `investment-strategy--continue` / `investment-strategy--back` | |

**Spec annotations (PPT 13):**
- *"Empfehlung basierend auf Ergebnis A&G, oder Abfrage unten wenn A&G noch nicht durchgeführt"* · *"Bei WA Story: komplette A&G"* (WA = Vermögensaufbau? unresolved — treat as: full A&G in that story).
- Open product questions: *"Ausgestaltung bei GRV anders? Handling falls Zurückhaltend ausgewählt wird? Text Anpassung bei Zurückhalten"* (Q-2).
- **Prototype delta:** 3 cards implemented (`risk_approach`); no recommendation mode, no info popovers.

---

## S-12 · `esg-basic` — Wie nachhaltig darf es sein?

| | |
|---|---|
| **Sources** | PDF `ID: EsgBasic` (once `EsgBasics`, [D-17](README.md#d-17)) · PPT 14–16 · flow step `esg` → section `esg_preference` |
| **Status** | PARTIAL |

- **Intent:** coarse sustainability preference (3 options); entry point to the detailed regulatory question set.
- **Entry:** `investment-strategy`.
- **Exit:** → `esg-details` (via *"Nachhaltigkeitspräferenzen individuell festlegen"*) or → `etf`.
- **Gating:** marked *Optional* (PPT 14). PDF: `only when clicking on "präferenzen festlegen"` opens S-13.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `esg-basic--root` | |
| Title | `esg-basic--title` | *"Wie nachhaltig darf es sein?"* |
| Option market breadth | `esg-basic--option-NONE` | *"Ich möchte auf die gesamte Breite des Marktes setzen"* |
| Option exclusively sustainable | `esg-basic--option-ART_8_9_ONLY` | *"Ich investiere ausschließlich in nachhaltige Anlageformen"* |
| Option overweight | `esg-basic--option-PREFER_ESG` | *"Ich möchte nachhaltige Anlageformen übergewichten"* |
| Details entry | `esg-basic--btn-details` | *"Nachhaltigkeitspräferenzen individuell festlegen"* → S-13 |
| Info popovers | `esg-basic--info-{NONE\|ART_8_9_ONLY\|PREFER_ESG\|details}` | 4 mouseover texts, see below |
| Continue / Back | `esg-basic--continue` / `esg-basic--back` | |

**Mouseover texts (PPT 14, verbatim):**
1. exclusively: *"…ausschließlich aus Fonds mit definierten Nachhaltigkeitsmerkmalen nach EU-Offenlegungsverordnung (Artikel 8 und 9). Klassische, nicht-nachhaltige Fonds werden ausgeschlossen."*
2. overweight: *"Nachhaltige Fonds bilden einen Schwerpunkt … kombinieren nachhaltige Anlagen mit klassischen Fonds."*
3. breadth: *"…nutzt die komplette Marktbreite, ohne Nachhaltigkeitskriterien besonders zu gewichten."*
4. details: *"…genauer bestimmen, welche Nachhaltigkeitsaspekte (z. B. Umwelt, Soziales, Unternehmensführung) wichtig sind…"*

**Warning popup (PPT 16)** — after strict selection: `esg-basic--popup` / `--popup-confirm` / `--popup-cancel` — *"Durch die Auswahl individueller Nachhaltigkeitskriterien kann sich die Anzahl der verfügbaren Fonds deutlich reduzieren… Wollen Sie dennoch fortfahren?"* → [D-12](README.md#d-12).

**Prototype delta:** 3 options implemented (`esg_preference`: `NONE` / `PREFER_ESG` / `ART_8_9_ONLY`); no details entry, no popup, no popovers.

---

## S-13 · `esg-details` — Nachhaltigkeitspräferenzen individuell festlegen

| | |
|---|---|
| **Sources** | PDF `ID: EsgDetails` · PPT 17–18 |
| **Status** | PLANNED |

- **Intent:** the regulatory preference question set (deckblatt *"NACHHALTIGKEITSPRÄFERENZEN FESTLEGEN"*) incl. multi-select of preference characteristics.
- **Entry:** `esg-basic--btn-details` only.
- **Exit:** → `etf` (*"Falls Nachhaltigkeitspräferenzen individuell festgelegt werden, werden diese mit Klick auf weiter übernommen"* — with reduced fund universe).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `esg-details--root` | |
| Q forms known | `esg-details--option-forms-ja` / `esg-details--option-forms-nein` | *"Ja" / "Nein, die Unterschiede wurden mir aber innerhalb dieser Beratung erklärt."* |
| Q characteristics | `esg-details--option-{value}` | multi-select: *keine besondere Präferenz · ESG-Strategieprodukte/PAI · Auswirkungsbezug Nachhaltigkeit ESG · Auswirkungsbezug Ökologie E · Nicht relevant* |
| Error popup | `esg-details--popup` | *"…kein passendes Beispiel Portfolio generieren. Bitte passen Sie ihre Auswahl an, oder kontaktieren Sie einen Berater…"* |
| Popup advisor | `esg-details--popup-advisor` | *"Berater finden"* |
| Popup back | `esg-details--popup-back` | *"Zurück"* |
| Continue / Back | `esg-details--continue` / `esg-details--back` | |

**Spec annotations (PPT 17–18):** *"Nicht vollständige Darstellung – siehe Datei „Nachhaltigkeitspräferenz Fragen""* (file not in repo, Q-7) · *"Fondsuniversum allerdings stark eingeschränkt, daher potentielles Handling nötig. Error Handling wenn zu wenig Fonds übrig"* → [D-12](README.md#d-12).

---

## S-14 · `etf` — Indextracker / ETF-Bevorzugung

| | |
|---|---|
| **Sources** | PDF `ID: ETF` (+ annotation `only for "Komfort"`, [D-08](README.md#d-08)) · PPT 19 · flow step `etf` → section `etf_preference` |
| **Status** | PARTIAL |

- **Intent:** ETF stance — none / prefer / only (drives the eligibility filter).
- **Entry:** `esg-basic` or `esg-details`.
- **Exit:** → `customer-type`.
- **Gating:** **unresolved** — PDF annotates `only for "Komfort"` but PPT 19 and both flow variants ask everyone ([D-08](README.md#d-08)).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `etf--root` | |
| Title | `etf--title` | *"Sollen Indextracker / ETFs bevorzugt in Ihr Fondsportfolio eingehen?"* |
| Option no preference | `etf--option-no_preference` | *"Fondsportfolio ohne Bevorzugung von Indextracker / ETFs auswählen"* |
| Option exclusively | `etf--option-etf_only` | *"Ausschließlich Indextracker / ETFs im Fondsportfolio auswählen"* |
| Option prefer | `etf--option-prefer_etf` | *"Indextracker / ETFs im Fondsportfolio bevorzugen"* |
| Info popovers | `etf--info-{no_preference\|etf_only\|prefer_etf}` | 3 mouseover texts (PPT 19): only = *"…nur aus kostengünstigen, passiv gemanagten Fonds (ETFs/Indexfonds)…"*; prefer = *"…zentrale Rolle und werden bevorzugt eingesetzt. Ergänzend können aktiv gemanagte Fonds hinzukommen…"*; none = *"…keine besondere Präferenz… flexibel kombinieren."* |
| Continue / Back | `etf--continue` / `etf--back` | |

**Prototype delta:** 3 options implemented (`etf_preference`); no popovers.

---

## S-15 · `customer-type` — Komfort- oder Aktiv-Kunde

| | |
|---|---|
| **Sources** | PDF `ID: CustomerType` · PPT 20 · flow step `activity` |
| **Status** | IMPLEMENTED |

- **Intent:** self-service level. Komfort → experts build the portfolio; Aktiv → region/theme steps follow.
- **Entry:** `etf`.
- **Exit:** Komfort → **`result` directly** (*"Bei dieser Auswahl wird das Portfolio direkt erstellt"*, PPT 20; variant B: `showIf aktivitaet != Komfort-Kunde` on downstream steps); Aktiv → `region-gate`.
- **Gating:** gates S-16…S-19.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `customer-type--root` | |
| Title | `customer-type--title` | *"Wie aktiv möchten Sie sich Ihr Fondsportfolio gestalten?"* |
| Option Komfort | `customer-type--option-komfort` | *"Ich bin Komfortkunde und möchte mich nicht um meine Vorsorge kümmern müssen — Management durch die Provinzial Experten"* |
| Option Aktiv | `customer-type--option-aktiv` | *"Ich bin Aktiv-Kunde und möchte die Investmentanlage mitgestalten — Selbst zusammenstellen und anpassen"* |
| Info Komfort | `customer-type--info-komfort` | mouseover 1: *"Sie überlassen die Zusammenstellung und laufende Anpassung des Portfolios den Provinzial-Experten…"* |
| Info Aktiv | `customer-type--info-aktiv` | mouseover 2 — **empty in the dump** (Q-3) |
| Continue / Back | `customer-type--continue` / `customer-type--back` | |

**Prototype delta:** implemented (values `Komfort-Kunde` / `Aktiv-Kunde`); variant A does not skip for Komfort (linear).

---

## S-16 · `region-gate` — Region gewichten?

| | |
|---|---|
| **Sources** | PPT 21 · PDF annotation `only for "Aktiv-Kunde"` on the following screens · flow step `region_gate` (variant B) |
| **Status** | IMPLEMENTED (B) |

- **Intent:** cheap opt-out before the region picker.
- **Entry:** `customer-type` (Aktiv only).
- **Exit:** Ja → `regions`; Nein → `theme-gate`.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `region-gate--root` | |
| Title | `region-gate--title` | *"Möchten Sie eine Region in Ihrem Portfolio besonders gewichten?"* |
| Option Nein | `region-gate--option-nein` | *"Nein, ich habe keine regionalen Präferenzen"* |
| Option Ja | `region-gate--option-ja` | *"Ja, eine bestimmte Region ist mir sehr wichtig"* |
| Info popovers | `region-gate--info-{nein\|ja}` | PPT 21 texts: 1 = *"…breit über verschiedene Weltregionen gestreut…"*; 2 = *"Sie legen einen regionalen Fokus fest (z. B. Europa oder Schwellenländer)…"* |
| Continue / Back | `region-gate--continue` / `region-gate--back` | |

---

## S-17 · `regions` — Regionenauswahl

| | |
|---|---|
| **Sources** | PDF `ID: RegionTypes` (also `Regions`) · PPT 22 · flow step `regions` → section `preferred_regions` |
| **Status** | PARTIAL |

- **Intent:** pick the regional focus (multi-select with budget).
- **Entry:** `region-gate` = Ja. PDF: `only "Ja"`.
- **Exit:** → `theme-gate`.
- **Gating:** max **1** per spec (*"Maximal 1 Regionen auswählbar"*, PPT 22) vs. prototype `max: 2` ([D-01](README.md#d-01)). DEFENSIVE excludes `asia` + `emerging_markets` per PPT 22 ([D-05](README.md#d-05)). Cross-dimension budget DEF 1 / BAL 2 / OPP 3 (implemented in schema + [`app.js`](../../static/js/app.js)).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `regions--root` | |
| Title | `regions--title` | *"Welche Region möchten Sie in Ihrem Fondsportfolio besonders gewichten?"* |
| Max note | `regions--note-max` | *"Maximal 1 Regionen auswählbar"*; budget note *"Based on your risk approach you can select up to {max} option(s)."* |
| Option Deutschland | `regions--option-germany` | |
| Option Europa | `regions--option-europe` | |
| Option Nordamerika | `regions--option-north_america` | |
| Option Asien/Pazifik | `regions--option-asia` | **disabled when profile = Zurückhaltend** (spec) |
| Option Schwellenländer | `regions--option-emerging_markets` | **disabled when profile = Zurückhaltend** (spec) |
| Disabled reason | `regions--option-{value}-disabled-reason` | a11y explanation when option is gated off |
| Continue / Back | `regions--continue` / `regions--back` | at least one selection required (Ja path) |

**Spec annotations (PPT 22):** budget rule verbatim — *"Defensiv max. 1; Ausgewogen max. 2 (je max. 1 Region und max. 1 Thema); Chancenorientiert max. 3 (egal ob 2 Regionen und 1 Thema oder 1 Region und 2 Themen)"* → [D-01…D-05](README.md#gaps--product-decisions).

---

## S-18 · `theme-gate` — Themen gewichten?

| | |
|---|---|
| **Sources** | PDF `ID: Industries` · PPT 23 · flow step `themes_gate` (variant B) |
| **Status** | IMPLEMENTED (B) |

- **Intent:** opt-out before the theme picker.
- **Entry:** `regions` or `region-gate` = Nein.
- **Exit:** Ja → `themes`; Nein → `result`.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `theme-gate--root` | |
| Title | `theme-gate--title` | *"Welche Themen und Trends sollen in Ihrem Fondsportfolio abgebildet sein?"* |
| Option Nein | `theme-gate--option-nein` | *"Nein, ich habe keine thematischen Präferenzen"* |
| Option Ja | `theme-gate--option-ja` | *"Ja, bestimmte Themen und Trends sind mir sehr wichtig"* |
| Info popovers | `theme-gate--info-{nein\|ja}` | PPT 23 texts (no strategy vs. Zukunftsthemen) |
| Continue / Back | `theme-gate--continue` / `theme-gate--back` | |

---

## S-19 · `themes` — Themenauswahl

| | |
|---|---|
| **Sources** | PDF `ID: IndustryTypes` · PPT 24 · flow step `themes` → section `preferred_themes` |
| **Status** | PARTIAL |

- **Intent:** pick up to N thematic satellites.
- **Entry:** `theme-gate` = Ja. PDF: `only "Ja"`.
- **Exit:** → `result`.
- **Gating:** *"Maximal 2 Themen auswählbar"* (prototype `max: 2` ✔). DEFENSIVE: **no themes at all** (PPT 24) vs. budget 1 ([D-02](README.md#d-02)). Budget family → [D-03](README.md#d-03)/[D-04](README.md#d-04). Label/value mapping → [D-07](README.md#d-07).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `themes--root` | |
| Title | `themes--title` | same as S-18 title |
| Max note | `themes--note-max` | *"Maximal 2 Themen auswählbar"* + budget note |
| Option Rohstoffe | `themes--option-commodities` | |
| Option Ökologie & Erneuerbare Energie | `themes--option-sustainability` | **mapping divergence [D-07](README.md#d-07)** |
| Option Megatrends | `themes--option-megatrends` | |
| Option Gesundheit & Pflege | `themes--option-healthcare` | |
| Option Infrastruktur | `themes--option-infrastructure` | |
| Option KI & Robotics | `themes--option-ai_robotics` | |
| Option Sicherheit & Verteidigung | `themes--option-defense` | |
| Option Wasser | `themes--option-water` | |
| Option Technologie | `themes--option-technology` | |
| Option Dividenden | `themes--option-dividends` | |
| Info popovers | `themes--info-{value}` | 10 mouseover texts (PPT 24, one per theme — long-form descriptions) |
| Continue / Back | `themes--continue` / `themes--back` | at least one selection required (Ja path) |

**Spec annotations (PPT 24):** mouseover examples — Megatrends: *"Langfristige, globale Entwicklungen wie Digitalisierung, Demografie oder Urbanisierung…"*; Rohstoffe: *"…Energie, Metalle, Industrie- und Agrarrohstoffe. Geeignet zur Diversifikation und als Schutz vor Inflation…"*. Full set in the dump.

---

## S-20 · `result` — Ihr Beispiel Portfolio

| | |
|---|---|
| **Sources** | PDF *"Ihr Beispiel Portfolio"* · PPT 25 (+ 29 zoom variant) · prototype `results-view` Summary tab + fund table |
| **Status** | PARTIAL |

- **Intent:** generated portfolio proposal; entry to all analysis tabs and the save flow.
- **Entry:** `themes` / `theme-gate` Nein / `customer-type` Komfort / `portfolio-load` / StarterKids strategy step.
- **Exit:** tabs → S-21/S-22/S-23; → `save`; Zurück re-enters the journey.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `result--root` | |
| Fund count | `result--count` | *"Alle Fonds (5)"* |
| Tab Zusammenfassung | `result--tab-summary` | default tab |
| Tab Stresstest-Ergebnis | `result--tab-stress` | → S-23 (PPT 25 lists 5 tabs: *Zusammenfassung · Stresstest-Ergebnis · Präferenzen · Volatilität · Rendite*; prototype has 4) |
| Tab Präferenzen | `result--tab-preferences` | → S-21 |
| Tab Volatilität | `result--tab-volatility` | volatility display |
| Tab Rendite | `result--tab-performance` | → S-22 |
| Fund row | `result--fund-{ISIN}` | name + ISIN + weight (e.g. *Provinzial Aktien Welt, DE000A403EK7, 40 %*) |
| Fund expand | `result--fund-{ISIN}-expand` | *"Bei Aufklappen werden die Fondsinformationen angezeigt"* |
| Fund actions menu | `result--fund-{ISIN}-menu` | *"Über die Punkte können einzelne Fonds ausgetauscht oder gelöscht werden"* — **not implemented** ([D-14](README.md#d-14)) |
| Fund exchange | `result--fund-{ISIN}-exchange` | PLANNED |
| Fund remove | `result--fund-{ISIN}-remove` | PLANNED |
| Headline metrics | `result--metric-rendite` / `result--metric-volatilitaet` | *"+9,85 % (10 J p.a.)"* / *"X,XX % (5 J p.a.)"* |
| Profile chart | `result--chart-asset-classes` / `result--chart-regions` | Anlageklassen + Regionen donuts (PPT 25); slide 29 adds *"vertieften Informationen zu Anlageklassen, Regionen, ggf. Themen"* — themes breakdown missing |
| Continue / Back | `result--continue` / `result--back` | |

---

## S-21 · `preferences-summary` — Ihre Präferenzen

| | |
|---|---|
| **Sources** | PPT 26 · prototype Preferences tab |
| **Status** | PARTIAL |

- **Intent:** echo all collected answers for confirmation.

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `preferences-summary--root` | |
| Row per field | `preferences-summary--row-{field}` | fields per PPT 26: *Anlageziel · Beitragsart · Risikoklasse · Produkt · Nachhaltigkeit · ETF-Bevorzugung · Mitgestaltung Portfolio · Regionale Schwerpunkte · Thematische Schwerpunkte · Investmentstrategie* |

**Note:** the *Investmentstrategie* row (*"Wachstum"*) has no prototype counterpart — the schema stores `risk_approach` but no separate strategy concept ([D-11](README.md#d-11)).

---

## S-22 · `performance` — Renditeentwicklung

| | |
|---|---|
| **Sources** | PPT 27 · prototype Performance tab |
| **Status** | PARTIAL |

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `performance--root` | |
| Return figure | `performance--metric-rendite` | *"+9,85 % (p.a.)"* |
| Inflation figure | `performance--metric-inflation` | *"− 2,67 % (p.a.)"* |
| Cost figure | `performance--metric-costs` | *"− 0,16 % (p.a.)"* |
| Period switch | `performance--period-{3y\|5y\|10y}` | spec: *3J · 5J · 10J*; prototype: 1y/3y/5y/10y/si |

---

## S-23 · `stress-test` — Stresstest

| | |
|---|---|
| **Sources** | PPT 28 · prototype Performance-tab stress overlay (`data/stress_periods.json`) |
| **Status** | PARTIAL |

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `stress-test--root` | |
| Scenario toggle | `stress-test--scenario-{id}` | spec scenarios: *COVID-19* · *INFLATION* |

---

## S-24 · `save` — Portfoliovorschlag speichern

| | |
|---|---|
| **Sources** | PDF *"HERE IS YOUR ID + PDF DOWNLOAD / Portfoliovorschlag speichern / Upload JSON to docRepository (Provinzial can call JSON by ID)"* · prototype portfolio persistence + ID display |
| **Status** | PARTIAL |

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `save--root` | |
| Save button | `save--submit` | persists proposal |
| ID display | `save--id-display` | *"HERE IS YOUR ID"* — prototype shows UUID (`display-port-id`) |
| PDF download | `save--download-pdf` | **PLANNED** ([D-15](README.md#d-15)) |
| Upload status | `save--upload-status` | *"Upload JSON to docRepository"* — **PLANNED** |

---

## S-25 · `death-protection` — Todesfallschutz (branch)

| | |
|---|---|
| **Sources** | PDF `ID: DeathProtection` · PPT 37 |
| **Status** | PLANNED |

- **Intent:** GenDep-only question; Ja restricts the fund universe.
- **Entry:** `product-selection-gendep` = Generationen Depot.
- **Exit:** → `payments` (branch variant).

| Element | testid | Spec |
|--------|--------|------|
| Screen root | `death-protection--root` | |
| Title | `death-protection--title` | *"Wünschen Sie im Produkt ein Todesfallschutz?"* |
| Option Ja / Nein | `death-protection--option-ja` / `death-protection--option-nein` | Ja → restricted portfolio |
| Continue / Back | `death-protection--continue` / `death-protection--back` | |

**Spec annotation (PPT 37):** *"Hintergrund dieser Frage: bei GenDep mit TFS gibt es nur ein eingeschränktes Fondsportfolio."*

---

## S-26 · Kapitalanlage branch — `objective-capital-growth`, `product-selection-gendep`, `payments` variants

| | |
|---|---|
| **Sources** | PDF `ID: PensionInsuranceTypeID: InvestmentObjectiveCapitalGrowth` · PPT 31/35 (goal variant), 36/40 (GenDep/StarterKids), 32/38 (one-off), 41 (StarterKids amounts), 39/42 (strategy variants) |
| **Status** | PLANNED |

- **Intent:** the *Kapitalanlage* goal replaces the goal cards (*Vererben/verschenken* · *Optimiert anlegen*), the product cards (*Generationen Depot* · *Starter Kids*), and the amount bounds.
- **Sequence:** `objective-capital-growth` → `product-selection-gendep` → [`death-protection` iff GenDep] → `payments` (one-off 5.000 €…1.000.000 €, markers from Tarifrechner; StarterKids: Sparrate 25 € preselected…max 200 €, one-off 250…999.999 €) → `investment-strategy` → *"Bei Klick auf Weiter wird das Portfolio direkt erstellt"* (39) / *"...normale VM / AV Strecke weitergegangen"* (42) → `result`.

| Element | testid | Spec |
|--------|--------|------|
| Option Vererben/verschenken | `objective-capital-growth--option-vererben` | *"Vermögen sorgenfrei vererben und verschenken."* |
| Option Optimiert anlegen | `objective-capital-growth--option-optimiert` | *"Geld rendite- und steueroptimiert anlegen."* |
| Card Generationen Depot | `product-selection-gendep--option-generationen_depot` | *"Vermögensplan für Generationen"* + 3 bullets |
| Card Starter Kids | `product-selection-gendep--option-starter_kids` | *"Vorsorge für die Zukunft unserer Kinder"* + 3 bullets |
| StarterKids Sparrate | `payments--input-sparrate` | min 25 € (preselected) · **max 200 €/Monat (2.400 jährlich)** |
| StarterKids Einmalbeitrag | `payments--input-einmalbeitrag_sk` | **250–999.999 €** |
| Duration | `payments--input-laufzeit` | 12–50+ J, default 30 |

**Spec annotations:** all branch screens carry the Endkunden-web-only note; A&G buttons labelled *"Angemessenheits- und Geeignetheitsprüfung"* (36/40). Full divergence record in [D-16](README.md#d-16).

---

## Prototype chrome (not in PDF/PPT spec)

| Element | testid | Notes |
|--------|--------|-------|
| Flow progress bar | `flow--progress` | progress fill + label (visible steps only) |
| Flow back / next | `flow--back` / `flow--continue` | global nav under every flow step |
| Language switch | `chrome--lang-select` | en/de |
| Active session banner | `chrome--session-banner` | shows active portfolio id |
| Error view | `chrome--error` | API failure display |
| Restart | `chrome--restart` | back to welcome |
