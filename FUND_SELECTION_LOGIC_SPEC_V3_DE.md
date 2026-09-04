# Fondsauswahllogik — Spezifikation v3 (DE)
**Quelle:** Provinzial „Fondsauswahllogik – Fondskompass" (März 2026); v2 überarbeitet 2026-08-17/18
**Implementierung:** [`funds_portfolio/portfolio/decision_engine.py`](funds_portfolio/portfolio/decision_engine.py)
**Vorgängerversion:** v2 archiviert unter [`notes/FUND_SELECTION_LOGIC_SPEC_V2.md`](notes/FUND_SELECTION_LOGIC_SPEC_V2.md)
**Autoritative Sprachfassung:** [`FUND_SELECTION_LOGIC_SPEC_V3.md`](FUND_SELECTION_LOGIC_SPEC_V3.md) (EN). Diese Übersetzung ist specificationstreu; im Zweifel gilt die englische Fassung.

> **Kernänderung v3:** Die Fondsauswahl ist ein **zweistufiger, abdeckungsorientierter, rein additiver**
> Durchlauf über eine einzige Rangliste (Schritt 7). Die v2-Mechanismen „Garantie per Force-Insert
> mit Protection-Set" und „Kappen nach der Auswahl mit Abwicklung" sind entfernt. Quoten werden
> als *Skip während der Auswahl* durchgesetzt, nie als Abwicklung danach — die Portfoliogröße ist
> damit konstruktionsbedingt sicher.

---

## Überblick

Die Fondsauswahllogik läuft in drei sequenziellen Phasen; jede Phase wird vollständig im
Decision Trace protokolliert:

| Phase | Ziel | Output |
|-------|------|--------|
| **1 — Filter** | Ungeeignete Fonds ausschließen (Datenqualität, ESG, ETF, Risikoband) | Reduziertes Fondsuniversum |
| **2 — Scoring** | Verbleibende Fonds bewerten: quantitative Basis + Präferenz-Boosts | Eine Rangliste (das Ranking) |
| **3 — Portfoliokonstruktion** | Zweistufige Auswahl von 5 Fonds, danach Core-Satellite-Gewichtung | 5-Fonds-Portfolio mit Allokationen + vollständiges Entscheidungsprotokoll |

---

## Phase 1 — Filter

Fonds durchlaufen sequenzielle Hartfilter vor dem Scoring. Der Trace protokolliert je
Filter die Counts vor/nach.

### Schritt 0 — Pflichtfelder-Filter

Ausschluss von Fonds ohne: `isin`, `name`, `yearly_fee`, `sharpe_ratio`,
`max_drawdown`, `srri` (oder `risk_level`), `volatility`. Die regulatorische
Vertriebseignung (Freigabe Deutschland, kein Abwicklungszustand) ist durch die
Datenbank-Kuration sichergestellt.

> Spätere Stufen tolerieren fehlende Einzelmetriken über SRRI-Proxies (Schritt 5); der
> Pflichtfelder-Gate hält das Universum datenvollständig.

### Schritt 1 — ESG-Filter

ESG ist eine Dreifach-Präferenz (`esg_preference`); Artikel 8 und 9 gelten zusammen als
„nachhaltig" (abgeleitet aus `esg_label`):

- **`ART_8_9_ONLY`** — Hartfilter: nur `SFDR_ARTICLE_8` / `SFDR_ARTICLE_9`.
- **`PREFER_ESG`** — kein Ausschluss; nachhaltige Fonds erhalten einen Scoring-Boost (Schritt 6).
- **`NONE`** — ESG wird vollständig ignoriert (Legacy-Antwortwerte werden auf diese drei normalisiert).

### Schritt 2 — ETF-Präferenz-Filter

- **`etf_only`** — Hartfilter: nur Fonds mit `is_etf`. Verbleiben nach allen Filtern
  weniger als 5 ETFs, greift der ETF-only-Fallback (Ende von Schritt 7).
- **`prefer_etf`** — kein Ausschluss; ETFs erhalten einen Scoring-Boost (Schritt 6).
- **`no_preference`** — keine Aktion.

### Schritt 3 — Risikoband-Filter

Abbildung von `risk_approach` (conservative / moderate / aggressive) auf ein
dreistufiges Profil mit den Bändern der autoritativen Folie (Schritt 8 des Source-Decks):

| Parameter | DEFENSIVE | BALANCED | OPPORTUNITY (= chancenorientiert) |
|-----------|-----------|----------|-----------------|
| SRRI (oder `risk_level`) | 1–3 | 2–5 | 4–7 |
| Volatilität p. a. | ≤ 8 % | 5–15 % | ≥ 10 % (keine Obergrenze) |
| Max Drawdown | < 15 % | < 30 % | < 50 % |

Die Bänder überlappen bewusst, um harte Grenzausschlüsse zu vermeiden.

### Schritt 4 — Regions- und Themenpräferenzen *(weich — kein Filter)*

Regions- und Themenpräferenzen schließen nie Fonds aus. Sie wirken über (a) Scoring-Boosts
(Schritt 6), (b) den Abdeckungsdurchlauf (Schritt 7, Durchlauf 1) und (c) den
Allokations-Tilt (Schritt 10).

### Lockerungen und Warnungen *(durch `min_candidates` gesteuert)*

- **Risikoband-Lockerung:** Bei weniger als `min_candidates` Fonds wird das Band um
  ±1 SRRI und ±5 % Volatilität geweitet. Derzeit **deaktiviert** (`min_candidates = 0`);
  ein zu restriktives Universum fällt ehrlich durch, statt still ausgeweitet zu werden.
- **Final-Fund-Floor:** Mit `min_candidates > 0` wird bei zu wenigen Fonds auf den
  Pre-Risk-Pool zurückgefallen (ebenfalls standardmäßig deaktiviert).
- **Universum-Warnung:** Bei 0 < verbleibend < 3 enthält der Trace eine Warnung, dass
  das Portfolio Fonds am Rand des Eignungsbereichs enthalten kann.

---

## Phase 2 — Scoring

### Schritt 5 — Basis-Qualitätsscore (0–100)

Jeder geeignete Fonds erhält einen zusammengesetzten Score aus drei min-max normalisierten
Metriken (Normalisierung über das geeignete Universum der aktuellen Session, Skala 0–10):

```
base = (Sharpe_norm × 5.0) + (MDD_norm × 3.0) + (TER_norm × 2.0)
```

| Komponente | Metrik | Gewicht | Richtung |
|------------|--------|---------|----------|
| Risikoadjustierte Rendite | Sharpe Ratio | 50 % | höher ist besser |
| Drawdown-Schutz | Maximum Drawdown | 30 % | niedriger ist besser (invertiert) |
| Kosteneffizienz | TER (`yearly_fee`) | 20 % | niedriger ist besser (invertiert) |

Proxies bei fehlender Metrik im Scoring: MDD ← `SRRI_MDD_PROXY[srri]`; Volatilität ←
`SRRI_VOL_PROXY[srri]` (verwendet in der Allokation).

**Sortierung des Rankings** (deterministisch): Final-Score ↓, dann Sharpe ↓, dann
Gebühr ↑, dann ISIN ↓.

### Schritt 6 — Präferenz-Boosts (auf die Basis)

**Begründung (v3.2-Nachjustierung):** Präferenzen werden inzwischen *strukturell*
umgesetzt, nicht über Ranking-Gewalt. Bevorzugte Regionen/Themen garantiert der
Abdeckungsdurchlauf (Schritt 7, Durchlauf 1); die Hartfilter (`ART_8_9_ONLY`,
`etf_only`) greifen in Schritt 1; und das Feasibility-Gating des Dialogs
(`funds_portfolio/dialog/feasibility.py`) formt den Antwortraum so, dass nur
erfüllbare Kombinationen angeboten werden. Boosts müssen die Auswahl daher nicht
mehr steuern und sind auf nominale Tie-Breaker reduziert: **ETF/ESG +6**
(ordnen nur nahezu gleichwertige Kandidaten um), **Region/Thema 0**
(vollständig deaktiviert — ein Boost abgedeckter Dimensionen würde nur das
qualitätsgetriebene Ranking von Durchlauf 2 verzerren).

| Boost | Bedingung | Wert (Default `BOOST_ELEVATORS`) |
|-------|-----------|------|
| ETF | `prefer_etf` und Fonds `is_etf` | **+6** |
| ESG | `PREFER_ESG` und `esg_label` ∈ {Art. 8, 9} | **+6** |
| Region | `fund.region` exakt in `preferred_regions` | **0** (deaktiviert) |
| Thema | `fund.theme` in `preferred_themes` (Platzhalter `NONE` deaktiviert) | **0** (deaktiviert) |

`ART_8_9_ONLY` ist ausschließlich Hartfilter (kein Boost). Ein Fonds kann mehrere Boosts
akkumulieren (z. B. ETF + ESG).

---

## Phase 3 — Portfoliokonstruktion

### Schritt 7 — Auswahl: zweistufig, abdeckungsorientiert, rein additiv

Die Auswahl operiert auf der einen Rangliste und **fügt nur hinzu**. Kein Fonds wird nach
der Auswahl abgewählt, geschützt oder getauscht — die Portfoliogröße kann nur Richtung
`final_fund_count` (5) wachsen. Die Größe ist konstruktionsbedingt sicher.

**Durchlauf 1 — Abdeckung (Präferenzen zuerst).** Die *vollständige* Rangliste wird in
Qualitätsreihenfolge durchlaufen; ein Fonds wird nur gewählt, wenn er auf mindestens
einen **noch nicht erfüllten** bevorzugten Wert (Region oder Thema) passt. Abbruch, wenn
alle bevorzugten Werte abgedeckt sind, kein Kandidat im gesamten Ranking existiert oder
das Portfolio voll ist.

- Die Garantie-Schalter steuern Durchlauf 1 je Dimension: `thematic_guarantee` (Themen),
  `regional_guarantee` (Regionen). Defaults: an.
- Eine Auswahl kann mehrere Werte gleichzeitig erfüllen (Fonds trägt bevorzugte Region
  *und* Thema); die Koinzidenz wird als `also_satisfies` protokolliert.
- Quotenkonforme Kandidaten haben Vorrang (Sweep A). Bleibt ein bevorzugter Wert unerfüllt
  und würde der einzige tragende Fonds die Quote verletzen, gilt **Abdeckung vor Quote**:
  der beste solche Fonds wird gewählt und der Verstoß explizit protokolliert (Sweep B).

**Durchlauf 2 — Auffüllung (beste Verbleibende).** Erneut vom Kopf des `top_k`-Pools —
ohne die bereits in Durchlauf 1 gewählten Fonds (der effektive Pool ist kleiner als
`top_k`) — werden die restlichen Plätze mit den besten Fonds unabhängig von
Präferenz-Matches gefüllt, vorbehaltlich der folgenden Constraints.

**Constraints — als Skip während der Auswahl durchgesetzt, nie als Abwicklung danach:**

| Constraint | Parameter (Default) | Geltung |
|------------|---------------------|---------|
| Max Fonds mit demselben konkreten bevorzugten Thema | `max_per_specific_theme` (2) | je Themen-**Wert** |
| Max Fonds aus derselben konkreten bevorzugten Region | `max_per_specific_region` (2) | je Regions-**Wert** |
| Max Fonds je Provider | `max_per_provider` (5 → faktisch aus) | Durchlauf 2 |
| Max Fonds je Asset-Kategorie | `max_per_category` (5 → faktisch aus) | Durchlauf 2 |

Die Quoten zählen **je konkretem Wert**: Sind zwei verschiedene bevorzugte Themen
abgedeckt (je 1 Fonds), blockiert das keines der beiden — übersprungen wird erst der
(Quota+1)-te Fonds *desselben* Themas bzw. derselben Region. Skip-Events führen die
aktuelle Auslastung mit, z. B. `theme:SUSTAINABILITY 2/2`.

**Anzahl-herstellende Lockerung.** Ist das Universum zu klein, um das Portfolio unter
allen Constraints zu füllen, hängt eine finale protokollierte Lockerung (`caps_relaxed`)
die besten verbleibenden Fonds ohne Rücksicht auf die Kappen an — **Vollständigkeit geht
vor Diversifikation**. Ein additives Anfügen kann das Portfolio nie verkleinern.

**ETF-only-Fallback.** Verbleiben bei `etf_only` weniger als 5 ETFs, werden restliche
Plätze aus dem bewerteten aktiven Pool (risikobandgefiltert) gefüllt und mit
`etf_not_available` gekennzeichnet („Aktiver Fonds — kein ETF innerhalb Ihrer Kriterien").

**Garantieergebnis.** Jeder bevorzugte Wert ist abgedeckt, sofern das Universum einen
Träger enthält; Werte ohne jeden Träger werden als `coverage_unfulfillable` mit Grund
protokolliert („kein Fonds mit diesem Wert im Universum" vs. „Portfolio gefüllt, bevor
dieser Wert abgedeckt werden konnte").

#### Durchgerechnetes Beispiel (echter Trace, echte Zahlen)

Antworten: aggressive · PREFER_ESG · prefer_etf · Regionen {germany, emerging_markets} ·
Themen {sustainability, defense}. Universum: 64 Fonds → 41 geeignete nach Filtern.

| # | Fonds | Basis | Final | Entscheidung |
|---|-------|-------|-------|--------------|
| 1 | Deka MSCI Germany Climate Change ESG CTB ETF | 35,5 | 265,5 | **Durchlauf 1** — trifft Thema sustainability + Region germany |
| 2 | Deka MSCI World Climate Change ESG CTB ETF | 64,3 | 224,3 | **Durchlauf 2** — nächstbester Score |
| 3 | Deka MSCI Europe Climate Change ESG CTB ETF | 56,1 | 216,1 | Übersprungen — `theme:SUSTAINABILITY 2/2` |
| 4 | Deka MSCI Japan Climate Change ESG CTB ETF | 51,7 | 211,7 | Übersprungen — `theme:SUSTAINABILITY 2/2` |
| 5 | Provinzial Aktien Welt | 92,1 | 182,1 | **Durchlauf 2** — nächstbester Score |
| 7 | Amundi MSCI Emerging Markets UCITS ETF | 51,7 | 166,7 | **Durchlauf 1** — trifft Region emerging_markets |
| 12 | Deka Europe Defense UCITS ETF | 41,7 | 156,7 | **Durchlauf 1** — trifft Thema defense |

Ergebnis: 5 Fonds (Ränge 1, 2, 5, 7, 12), **7/7 Präferenz-Items erfüllt**. Die Ränge 3/4
werden übersprungen (Quote voll) — niemals abgewählt, geschützt oder ersetzt. Rang 6
wird schlicht nicht erreicht.

### Schritt 8 — Core/Satellite-Klassifikation

`theme` gesetzt und ≠ `NONE` → **Satellite**; sonst **Core**. Erwartete Struktur:
2–4 Core-Positionen, 0–3 Satelliten (Satellitengesamtgewicht gedeckelt, Schritt 11).

### Schritt 9 — Gestaffelte Gewichtsbänder & inverse Volatilität

Rohe Gewichte sind invers-volatil (`1/vol`, SRRI-Proxy bei fehlender `volatility`),
anschließend auf die Stufenbänder geclippt:

| Position | Min | Max |
|----------|-----|-----|
| Core 1 (stabilster Core — höchste inverse Volatilität; Tier-Vergabe sortiert Cores nach inverser Volatilität, nicht nach Auswahlreihenfolge) | 25 % | 40 % |
| Core 2 | 15 % | 30 % |
| Core 3 | 10 % | 25 % |
| Core 4+ | 10 % | 15 % |
| Satellite (flach) | 10 % | 15 % |

### Schritt 10 — Regions-Tilt

Fonds, deren `region` eine bevorzugte Region ist, erhalten eine **relative
Gewichtserhöhung +20 % (× 1,2)**, gedeckelt auf ihr Stufenmaximum.

### Schritt 11 — Satelliten-Deckel & Normalisierung

Die Gewichte werden auf 100 % normalisiert; die Satellitensumme ist auf **30 %**
gedeckelt (nach der Normalisierung erneut erzwungen; der freigesetzte Spielraum geht
ausschließlich an Cores, bis zu deren Maxima).

### Schritt 12 — Mindestallokation & Ausgabe-Rundung

Ein Water-Filling-Floor garantiert jedem Fonds ≥ `min_allocation_percentage` (10 %);
ist das für die Fondsanzahl unmöglich, wird gleichverteilt. Die Allokationen werden auf
ganze Prozent gerundet; die größte Position nimmt den Rundungsrest auf (Summe = 100 %).

> Der 10 %-Floor gilt nach dem Clipping; mit mehreren Satelliten können Satelliten-Deckel
> und Normalisierung einzelne Fonds praktisch darunter drücken — der Water-Filling-Floor
> läuft zuletzt und stellt ihn wieder her, wo möglich.

---

## Risikoprofil-Referenz

### Begründung

- **DEFENSIVE:** Kapitalerhalt; Volatilität ≤ 8 % hält kurzfristige Schwankungen
  beherrschbar; keine hohe Aktienquote.
- **BALANCED:** Wachstum und Stabilität gleichgewichtet; SRRI 2–5 akzeptiert
  kurzfristige Verluste für mittelfristige Erträge.
- **OPPORTUNITY (chancenorientiert):** Renditemaximierung; keine Volatilitäts-Obergrenze,
  aber eine 10 %-Untergrenze verhindert das Füllen mit risikoarmen Anlagen.

### SRRI-Zuordnung

| SRRI | Volatilität (indikativ) | Profil |
|------|------------------------|--------|
| 1 | < 0,5 % | Defensive |
| 2 | 0,5–2 % | Defensive |
| 3 | 2–5 % | Defensive / Balanced |
| 4 | 5–10 % | Balanced |
| 5 | 10–15 % | Balanced / Opportunity |
| 6 | 15–25 % | Opportunity |
| 7 | > 25 % | Opportunity |

---

## Präferenz-Integration — Zusammenfassung

| Präferenz | Wert | Filter (Phase 1) | Boost (Phase 2) | Abdeckung (Schritt 7) | Allokation (Schritt 10) |
|-----------|------|------------------|-----------------|-----------------------|-------------------------|
| ESG | `ART_8_9_ONLY` | Hartfilter | — | — | — |
| ESG | `PREFER_ESG` | — | +6 (v3.2 Tie-Breaker) | — | — |
| ETF | `etf_only` | Hartfilter (+ Fallback) | — | — | — |
| ETF | `prefer_etf` | — | +6 (v3.2 Tie-Breaker) | — | — |
| Region | Werte (z. B. `asia`) | — | 0 (seit v3.2 deaktiviert) | Abdeckung in Durchlauf 1; Quote 2/Wert | Tilt × 1,2 |
| Thema | Werte (z. B. `defense`) | — | 0 (seit v3.2 deaktiviert) | Abdeckung in Durchlauf 1; Quote 2/Wert | Satellite-Klasse |

---

## Randfallbehandlung (implementiertes Verhalten)

| # | Fall | Verhalten |
|---|------|-----------|
| 1 | Weniger als 5 geeignete Fonds nach allen Filtern | Lockerungen sind an `min_candidates` gekoppelt (Default 0 = aus). Das Portfolio enthält dann so viele Fonds wie geeignet sind; unter 3 Fonds enthält der Trace eine Warnung. Die Auswahl reduziert die Anzahl nie weiter (Invariante, Schritt 7). |
| 2 | `etf_only` lässt weniger als 5 ETFs | Aktiven-Fonds-Backfill, jeder mit `etf_not_available` gekennzeichnet; Relaxation-Eintrag `etf_only_fallback` im Trace. |
| 3 | Starke Regionspräferenz | Quote `max_per_specific_region` = 2 je Wert als Skip; „Abdeckung vor Quote"-Verstoß möglich und protokolliert; Anzahl wird nur bei erzwungenem Universum über `caps_relaxed` hergestellt. |
| 4 | Thematische Fonds erhöhen das Portfoliorisiko | Strukturell behandelt: Satelliten wiegen je 10–15 %, Satellitensumme ≤ 30 %, inverse Volatilität dämpft volatile Fonds. (Keine MDD-Prüfung je Thema implementiert.) |
| 5 | Viele konfligierende Präferenzen / fast leere Schnittmenge | Durchlauf 1 deckt jeden Wert ab, der irgendwo einen Träger hat; restliche Plätze füllen mit den besten Fonds; unerfüllbare Werte werden protokolliert (`coverage_unfulfillable`) mit Grund. Eine „Präferenz-Hierarchie-Lockerung" ist nicht nötig, da kein Fonds verdrängt wird. |
| 6 | Mehr bevorzugte Werte als Plätze | Werte werden in Qualitätsreihenfolge ihres besten Trägers erfüllt; der Rest erscheint als unerfüllte Items in `preference_satisfaction` (7-Item-Einzelbericht). |

---

## Decision Trace & Explainability

Jede Stufe wird im `decision_trace` protokolliert und in der GUI (Tab „Präferenzen")
dargestellt. Auswahl-Events in Ausführungsreihenfolge:

| Event | Bedeutung |
|-------|-----------|
| `pass1_select` | Abdeckungs-Auswahl; enthält `matched` [{dimension, value}…], `also_satisfies`, optional `quota_breached` |
| `pass2_select` | Auffüll-Auswahl (nächstbester Score) |
| `selection_skip` | Skip in Durchlauf 2; `reason` ∈ {`provider_cap`, `category_cap`, `theme_quota`, `region_quota`}; `dimensions` führt die Auslastung mit (`theme:SUSTAINABILITY 2/2`) |
| `coverage_unfulfillable` | Bevorzugter Wert nicht abgedeckt; `reason`: kein Träger im Universum / Portfolio zuerst gefüllt |
| `caps_relaxed` | Anzahl-herstellende Lockerung; listet hinzugefügte ISINs |
| `etf_fallback_fill` | Aktiver Fonds hat einen ETF-only-Platz gefüllt |

Ranking-Kandidaten tragen einen Status: `selected` (Durchlauf 2),
`selected_pass1_coverage` (Durchlauf 1), `skipped_provider_cap`, `skipped_category_cap`,
`skipped_theme_quota`, `skipped_region_quota`, `not_reached`.

---

## Engine-Konfiguration (Defaults)

| Parameter | Default | Wirkung |
|-----------|---------|---------|
| `min_candidates` | 0 | deaktiviert alle Filter-Lockerungen |
| `top_k` | 65 | Durchlauf-2-Pool = Gesamtuniversum (Capping aus) |
| `final_fund_count` | 5 | Portfoliogröße |
| `max_per_provider` | 5 | Provider-Cap faktisch aus |
| `max_per_category` | 5 | Kategorie-Cap faktisch aus |
| `max_per_specific_theme` | 2 | Quote je bevorzugtem Themen-Wert |
| `max_per_specific_region` | 2 | Quote je bevorzugtem Regions-Wert |
| `min_allocation_percentage` | 10 | Gewichtsfloor je Fonds |
| `BOOST_ELEVATORS` | ETF 6 / ESG 6 / Region 0 / Theme 0 | Boosts aus Schritt 6 (alle auf Tie-Breaker-Niveau; Präferenzen werden strukturell umgesetzt — siehe Begründung) |
| `thematic_guarantee` / `regional_guarantee` | True / True | steuert Durchlauf 1 je Dimension |
| `theme_cap` / `regional_cap` | True / True | steuert die Quoten je Wert |

---

## Datenanforderungen

| Feld | Verwendung |
|------|------------|
| `srri` (oder `risk_level`) | Risikoband, Proxies |
| `volatility` (p. a. %) | Risikoband, inverse Volatilität |
| `max_drawdown` | Risikoband, Scoring |
| `yearly_fee` | Scoring (TER) |
| `sharpe_ratio` | Scoring |
| `is_etf` | ETF-Filter/Boost |
| `esg_label` | ESG-Filter/Boost |
| `region` | Regions-Boost, Abdeckung, Tilt |
| `theme` | Themen-Boost, Abdeckung, Core/Satellite-Klasse |
| `asset_class` | Kategorie-Cap |
| `provider` | Provider-Cap |

---

## Änderungsprotokoll gegenüber v2

| Aspekt | v2 | v3 (diese Spezifikation) |
|--------|----|--------------------------|
| Auswahl | Top-5-Pick + Force-Insert-Garantien mit Protection-Set + Kappen nach der Auswahl (Abwicklungen) | **zweistufige, abdeckungsorientierte, additive Auswahl; keine Abwicklungen, kein Protection-Set** |
| Präferenzabdeckung | Garantie-Tausch (konnte verkümmern, Portfolio verkleinern) | **Durchlauf 1 strukturell; anzahlsicher** |
| Diversifikations-Kappen | destruktive Abwicklungen nach der Auswahl | **Skips während der Auswahl + anzahl-herstellende Lockerung** |
| Quoten-Semantik | max 2 gleiche bevorzugte Region/Thema (Abwicklung) | gleiche Werte, je **konkretem** Wert (`max_per_specific_theme` / `max_per_specific_region`), als Skip mit Live-Auslastung im Trace |
| Boosts | ETF +5 / ESG +5 / Region +3 / Thema +3 | **ETF +6 / ESG +6 / Region 0 / Thema 0** (v3.2: alle Boosts auf Tie-Breaker-Niveau — Durchlauf-1-Abdeckung, Hartfilter und Dialog-Gating setzen Präferenzen strukturell um, Durchlauf 2 ordnet allein nach Qualität) |
| Anzahlsicherheit | nicht garantiert (5→3-Bug beobachtet) | **konstruktiv garantiert** (validiert: 0 auswahlbedingte Unterversorgungen im 1691-Antworten-Grid) |
| Trace-Vokabular | `thematic_insert`, `regional_insert`, `*_cap_drop` | `pass1_select`, `pass2_select`, `selection_skip`, `coverage_unfulfillable`, `caps_relaxed` |
| Lockerungen | immer aktive Weitung | an `min_candidates` gekoppelt (Default aus) |
| Scoring, Filter, Allokation, Risikobänder | — | unverändert gegenüber v2 |
