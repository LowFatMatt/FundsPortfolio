document.addEventListener('DOMContentLoaded', () => {

    // -------------------------------------------------------------------------
    // DOM refs
    // -------------------------------------------------------------------------
    const qForm           = document.getElementById('questionnaire-form');
    const qFields         = document.getElementById('questionnaire-fields');
    const loadingView     = document.getElementById('loading-view');
    const welcomeView     = document.getElementById('welcome-view');
    const formView        = document.getElementById('form-view');
    const resultsView     = document.getElementById('results-view');
    const errorView       = document.getElementById('error-view');
    const errorMessage    = document.getElementById('error-message');
    const submitBtn       = document.getElementById('submit-btn');
    const btnText         = document.getElementById('btn-text');
    const btnSpinner      = document.getElementById('btn-spinner');
    const restartBtn      = document.getElementById('restart-btn');
    const resumeForm      = document.getElementById('resume-form');
    const resumeIdInput   = document.getElementById('resume-id');
    const resumeError     = document.getElementById('resume-error');
    const startFreshBtn   = document.getElementById('start-fresh-btn');
    const activeSessionBanner = document.getElementById('active-session-banner');
    const activePortIdDisplay = document.getElementById('active-port-id');
    const scoreVal        = document.getElementById('score-val');
    const displayPortId   = document.getElementById('display-port-id');
    const decisionSummaryText = document.getElementById('decision-summary-text');
    const decisionFilters = document.getElementById('decision-filters');
    const userAnswersFilters = document.getElementById('user-answers-filters');
    const decisionTraceDetail = document.getElementById('decision-trace-detail');
    const langSelect      = document.getElementById('lang-select');
    const fundTableBody   = document.getElementById('fund-table-body');
    const fundCount       = document.getElementById('fund-count');
    const expandAllBtn    = document.getElementById('fund-expand-all-btn');
    const weightedFeeVal  = document.getElementById('weighted-fee-val');
    const assetClassLegend = document.getElementById('chart-asset-classes-legend');
    const regionLegend    = document.getElementById('chart-regions-legend');

    // -------------------------------------------------------------------------
    // Mode handling (see MODES.md §3)
    // `mode` selects the UI flavour; default is `flow`. Anything unrecognised
    // falls back to flow. Quick-Mode shows the full technical decision trace.
    // NOTE (interim): until the Phase 3 wizard lands, Flow-Mode reuses the
    // single-page form; the only visible difference today is trace visibility.
    // -------------------------------------------------------------------------
    const urlParams   = new URLSearchParams(window.location.search);
    const currentMode = (urlParams.get('mode') || 'flow').toLowerCase() === 'quick'
        ? 'quick'
        : 'flow';
    const showTracesForMode = currentMode === 'quick';
    document.body.dataset.mode = currentMode;

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------
    let currentPortfolioId = null;
    const supportedLangs   = ['en', 'de'];
    let currentLang        = 'en';
    let uiStrings          = {};
    let questionnaireSections = [];   // raw sections from /api/questionnaire
    let preferenceGating     = null;  // questionnaire-level preference_gating block

    // Flow-Mode (wizard) state — see MODES.md §3/§4
    const flowView         = document.getElementById('flow-view');
    const flowStepHost     = document.getElementById('flow-step-host');
    const flowProgressFill = document.getElementById('flow-progress-fill');
    const flowProgressLabel= document.getElementById('flow-progress-label');
    const flowBackBtn      = document.getElementById('flow-back-btn');
    const flowNextBtn      = document.getElementById('flow-next-btn');
    let flowConfig         = null;    // loaded flows/variant<X>.json
    let flowAnswers        = {};      // accumulated answers across steps
    let flowStepIndex      = 0;
    const flowVariant      = (urlParams.get('flowVariant') || 'A').toUpperCase();

    // Phase 2 — portfolio + chart state
    let lastPortfolio      = null;     // most recent /api/portfolio response
    let stressPeriodsCfg   = null;     // cached /api/config/stress-periods
    const stressEnabled    = {};       // id -> bool (toggle state)
    let selectedPerfPeriod = '10y';    // 1y | 3y | 5y | 10y | si
    let perfFetchToken     = 0;        // race-guard for async fetches
    let volFetchToken      = 0;

    // -------------------------------------------------------------------------
    // Bootstrap
    // -------------------------------------------------------------------------
    initLanguage();

    // -------------------------------------------------------------------------
    // Event listeners
    // -------------------------------------------------------------------------
    qForm.addEventListener('submit', handleSubmission);
    if (qFields) {
        qFields.addEventListener('click',  onQuickFormInteract);
        qFields.addEventListener('change', onQuickFormInteract);
    }
    restartBtn.addEventListener('click', resetApp);
    startFreshBtn.addEventListener('click', () => {
        currentPortfolioId = null;
        qForm.reset();
        clearResults();
        if (currentMode === 'flow') {
            showFlowView();
        } else {
            showFormView(null);
        }
    });
    resumeForm.addEventListener('submit', handleResume);

    if (flowNextBtn) flowNextBtn.addEventListener('click', flowNext);
    if (flowBackBtn) flowBackBtn.addEventListener('click', flowBack);
    if (flowStepHost) {
        flowStepHost.addEventListener('click',  onFlowStepInteract);
        flowStepHost.addEventListener('change', onFlowStepInteract);
    }

    if (expandAllBtn) {
        expandAllBtn.addEventListener('click', () => {
            const expand = !expandAllBtn.classList.contains('open');
            fundTableBody.querySelectorAll('.fund-expand-btn').forEach(btn => {
                btn.classList.toggle('open', expand);
                btn.setAttribute('aria-expanded', String(expand));
            });
            fundTableBody.querySelectorAll('.fund-detail-row').forEach(row => {
                row.classList.toggle('hidden', !expand);
            });
            setExpandAllState(expand);
        });
    }

    // Tab switching
    document.querySelectorAll('.result-tab').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn));
    });

    // -------------------------------------------------------------------------
    // i18n
    // -------------------------------------------------------------------------
    function normalizeLang(lang) {
        if (!lang) return 'en';
        const short = lang.toLowerCase().split('-')[0];
        return supportedLangs.includes(short) ? short : 'en';
    }

    function t(key, fallback) {
        return uiStrings[key] || fallback || key;
    }

    function applyTranslations() {
        document.documentElement.lang = currentLang;

        const titleEl = document.querySelector('title[data-i18n]');
        if (titleEl) document.title = t(titleEl.dataset.i18n, titleEl.textContent);

        document.querySelectorAll('[data-i18n]').forEach(el => {
            el.textContent = t(el.dataset.i18n, el.textContent);
        });
        document.querySelectorAll('[data-i18n-html]').forEach(el => {
            el.innerHTML = t(el.dataset.i18nHtml, el.innerHTML);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            el.placeholder = t(el.dataset.i18nPlaceholder, el.placeholder);
        });
        document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
            const label = t(el.dataset.i18nAriaLabel, el.getAttribute('aria-label') || '');
            el.setAttribute('aria-label', label);
            if (el.title) el.title = label;
        });
    }

    async function loadTranslations(lang) {
        try {
            const response = await fetch(`/static/i18n/${lang}.json`);
            if (response.ok) uiStrings = await response.json();
        } catch (err) {
            console.warn('Failed to load UI translations:', err);
        }
        applyTranslations();
    }

    function initLanguage() {
        const saved      = localStorage.getItem('lang');
        const browserLang = navigator.language || 'en';
        currentLang = normalizeLang(saved || browserLang);

        if (langSelect) {
            langSelect.value = currentLang;
            langSelect.addEventListener('change', async e => {
                currentLang = normalizeLang(e.target.value);
                localStorage.setItem('lang', currentLang);
                await loadTranslations(currentLang);
                await loadQuestionnaire();
            });
        }

        loadTranslations(currentLang).then(loadQuestionnaire);
    }

    // -------------------------------------------------------------------------
    // Questionnaire loading
    // -------------------------------------------------------------------------
    async function loadQuestionnaire() {
        try {
            const response = await fetch(`/api/questionnaire?lang=${currentLang}`);
            if (!response.ok) throw new Error(t('errors.load_questionnaire'));
            const data = await response.json();
            questionnaireSections = data.sections || [];
            preferenceGating      = data.preference_gating || null;
            renderForm(questionnaireSections);
            loadingView.classList.add('hidden');
            welcomeView.classList.remove('hidden');
        } catch (err) {
            showError(t('errors.load_questionnaire', 'Could not connect to server.'));
            console.error(err);
        }
    }

    // -------------------------------------------------------------------------
    // Form rendering — supports display_hint: "cards" | "chips" | default
    // -------------------------------------------------------------------------
    function renderForm(sections) {
        qFields.innerHTML = '';
        sections.forEach(section => qFields.appendChild(renderSection(section)));
    }

    // -------------------------------------------------------------------------
    // Feasibility gating v2 (dialog answer-space shaping)
    //
    // The questionnaire declares a top-level `preference_gating` block:
    //   { budget: { fields: [...], max_by_profile: { DEFENSIVE: 1, ... } },
    //     answer_to_profile: { conservative: "DEFENSIVE", ... },
    //     filters: [ { field, value, combo_key }, ... ] }
    // Every option of the budget sections carries `feasible` — precomputed
    // fund counts per (risk profile × filter combination):
    //   { DEFENSIVE: { any: n, esg8_9: n, etf: n, "esg8_9+etf": n }, ... }
    // Once the risk answer exists:
    //   * options with zero funds under the live combination render
    //     disabled-with-reason (never hidden — universe gaps stay visible),
    //   * the shared budget caps combined selections across the budget
    //     sections (per-section `max` remains an additional cap).
    // The selection engine keeps its hard filters as the backstop.
    // -------------------------------------------------------------------------
    // During a Quick-Mode re-render the DOM is wiped before the prefill
    // restores checked radios — the gathered answers are cached here so
    // gating still resolves while the sections re-render.
    let quickAnswersCache = null;

    function gatingAnswer(field) {
        // Flow-Mode: accumulated answers; Quick-Mode: live DOM state.
        if (flowConfig && !flowView.classList.contains('hidden')) return flowAnswers[field];
        const checked = qFields.querySelector(`[name="${field}"]:checked`);
        if (checked) return checked.value;
        if (quickAnswersCache && field in quickAnswersCache) return quickAnswersCache[field];
        // Unanswered radios have no :checked node — never fall back to the
        // first radio's value (it would leak "conservative" by DOM order).
        // Only a real <select> carries an explicit (possibly empty) value.
        const sel = qFields.querySelector(`select[name="${field}"]`);
        return sel ? sel.value : undefined;
    }

    function gatingProfile() {
        const gating = preferenceGating;
        if (!gating || !gating.answer_to_profile) return null;
        const answer = gatingAnswer('risk_approach');
        if (!answer) return null;
        return gating.answer_to_profile[answer] || null;
    }

    function liveComboKey() {
        const filters = (preferenceGating && preferenceGating.filters) || [];
        const active = new Set(
            filters.filter(f => gatingAnswer(f.field) === f.value).map(f => f.combo_key)
        );
        const esg = active.has('esg8_9');
        const etf = active.has('etf');
        return (esg && etf) ? 'esg8_9+etf' : (esg ? 'esg8_9' : (etf ? 'etf' : 'any'));
    }

    function budgetConfig() {
        return (preferenceGating && preferenceGating.budget) || null;
    }

    // Current multi-select answer of a budget field ("none" never counts).
    function gatingSelections(field) {
        if (flowConfig && !flowView.classList.contains('hidden')) {
            return Array.isArray(flowAnswers[field]) ? flowAnswers[field] : [];
        }
        const cached = quickAnswersCache && quickAnswersCache[field];
        if (Array.isArray(cached)) return cached;
        return Array.from(qFields.querySelectorAll(`[name="${field}"]:checked`))
            .map(el => el.value);
    }

    function selectedInBudget(field) {
        return gatingSelections(field).filter(v => String(v).toLowerCase() !== 'none').length;
    }

    // Decorated shallow copy with gating applied (or the section unchanged).
    function applyGating(section) {
        const profile = gatingProfile();
        if (!profile) return section;
        const combo = liveComboKey();
        const budget = budgetConfig();
        const maxByProfile = (budget && budget.max_by_profile) || {};
        const isBudgetSection = !!(budget && (budget.fields || []).includes(section.id));

        const options = (section.options || []).map(opt => {
            const perProfile = (opt.feasible || {})[profile];
            if (!perProfile || perProfile[combo] == null || perProfile[combo] > 0) return opt;
            // Zero under the live combination. Distinguish "never in the
            // universe" (zero under every combination) from "not available
            // for your answers" (zero only under the active filters).
            const allZero = Object.values(perProfile).every(n => n <= 0);
            return { ...opt, gated_unavailable: true, gated_reason: allZero ? 'no_funds' : 'answers' };
        });

        const out = { ...section, options, gated_profile: profile };

        // Shared budget: this section's effective cap is the remaining
        // budget after the other budget sections' selections; the static
        // per-section `max` remains an additional cap.
        if (isBudgetSection) {
            const total = maxByProfile[profile] != null ? maxByProfile[profile] : section.max;
            const used = (budget.fields || [])
                .filter(f => f !== section.id)
                .reduce((sum, f) => sum + selectedInBudget(f), 0);
            const remaining = Math.max(0, total - used);
            out.budget_total = total;
            out.budget_used  = used;
            const cap = section.max != null ? Math.min(section.max, remaining) : remaining;
            out.max = cap;
        }
        return out;
    }

    // Disabled-option reason text: distinguishes "no funds in the universe
    // at all" from "none under your current answers".
    function gatedReasonText(opt) {
        return opt.gated_reason === 'no_funds'
            ? t('ui.option_no_funds', 'No matching funds in the universe')
            : t('ui.option_unavailable_answers', 'Not available for your answers');
    }

    // Remove pre-filled selections that became infeasible because the user
    // back-navigated and changed a gating answer (risk/ESG/ETF), and trim
    // selections exceeding the shared budget. Surfaces a notice so the
    // adjustments are never silently lost. (Single-section steps assumed —
    // both budget sections render as their own flow steps.)
    function pruneInfeasibleSelections(sections) {
        let cleared = false;
        sections.forEach(section => {
            const effective = applyGating(section);
            if (!effective.gated_profile) return;

            const unavailable = new Set(
                (effective.options || [])
                    .filter(opt => opt.gated_unavailable)
                    .map(opt => String(opt.value))
            );

            const unselect = el => {
                el.classList.remove('selected');
                const input = el.querySelector('input');
                if (input) input.checked = false;
                cleared = true;
            };

            // 1) Availability: drop selections the current answers forbid.
            flowStepHost
                .querySelectorAll('.chip.selected, .question-card.selected')
                .forEach(el => {
                    if (unavailable.has(String(el.dataset.value))) unselect(el);
                });

            // 2) Budget: keep at most `effective.max` selections in this
            //    step (drop from the end — deterministic).
            if (effective.max != null) {
                let current = Array.from(
                    flowStepHost.querySelectorAll('.chip.selected, .question-card.selected')
                );
                while (current.length > effective.max) {
                    unselect(current.pop());
                }
            }
        });
        if (cleared) {
            showFlowError(t('ui.gating_cleared_selections',
                'Selection adjusted: some of the preferences you chose earlier are not available for your current answers.'));
            persistCurrentStep();
        }
    }

    // Quick-Mode: re-render gated sections whenever a gating-relevant answer
    // changes (risk / ESG / ETF / budget selections in the other section) so
    // disabled chips and the effective caps follow live. State is preserved
    // across the re-render via gather/applyPrefill.
    let lastQuickGatingSnapshot = null;
    function onQuickFormInteract() {
        if (!questionnaireSections.length) return;
        const answers = gatherAnswers(qFields);
        const budget = budgetConfig();
        const fields = ['risk_approach'];
        ((budget && budget.fields) || []).forEach(f => fields.push(f));
        ((preferenceGating && preferenceGating.filters) || [])
            .forEach(f => fields.push(f.field));
        const snapshot = fields
            .map(f => `${f}=${JSON.stringify(answers[f] || null)}`)
            .join('|');
        if (snapshot === lastQuickGatingSnapshot) return;
        lastQuickGatingSnapshot = snapshot;
        quickAnswersCache = answers;   // visible to gating helpers during render
        renderForm(questionnaireSections);
        applyPrefill(qFields, answers);
        quickAnswersCache = null;
    }

    // Render a single questionnaire section into a `.field-group` element.
    // Shared by the Quick-Mode form (loop) and the Flow-Mode wizard (one per step).
    function renderSection(rawSection) {
        const section = applyGating(rawSection);
        const group = document.createElement('div');
        group.className = 'field-group';

        // Label
        const label = document.createElement('label');
        label.className = 'field-label';
        label.htmlFor   = section.id;
        label.textContent = section.title || section.name || section.id;
        if (section.required) {
            const star = document.createElement('span');
            star.className   = 'required-star';
            star.textContent = ' *';
            label.appendChild(star);
        }
        group.appendChild(label);

        // Description
        if (section.description) {
            const desc = document.createElement('p');
            desc.className   = 'field-description';
            desc.textContent = section.description;
            group.appendChild(desc);
        }

        // Feasibility note: shared budget / caps for the answered risk
        // approach (L1 cardinality shaping).
        if (section.gated_profile) {
            let text = null;
            if (section.budget_total != null) {
                text = t('ui.gating_budget_note',
                    'For your risk approach you can combine up to {total} region/theme selections in total ({used} already chosen in the other step).')
                    .replace('{total}', section.budget_total)
                    .replace('{used}', section.budget_used);
            } else if (section.max != null) {
                text = t('ui.gating_max_note',
                    'Based on your risk approach you can select up to {max} option(s).')
                    .replace('{max}', section.max);
            }
            if (text) {
                const note = document.createElement('p');
                note.className   = 'field-gating-note';
                note.textContent = text;
                group.appendChild(note);
            }
        }

        const hint = section.display_hint || null;

        if (hint === 'cards' && section.type === 'single_select') {
            group.appendChild(renderCardGroup(section));
        } else if (hint === 'cards' && section.type === 'multi_select') {
            group.appendChild(renderMultiCardGroup(section));
        } else if (hint === 'chips') {
            group.appendChild(renderChipGroup(section));
        } else if (section.type === 'single_select') {
            group.appendChild(renderSelectField(section));
        } else if (section.type === 'multi_select') {
            group.appendChild(renderCheckboxList(section));
        } else if (section.type === 'number') {
            const wrap = document.createElement('div');
            wrap.className = 'flow-number';
            const input = document.createElement('input');
            input.type = 'number';
            input.id   = section.id;
            input.name = section.id;
            input.className = 'flow-number__input';
            if (section.min  != null) input.min  = section.min;
            if (section.step != null) input.step = section.step;
            if (section.value != null) input.value = section.value;
            if (section.required) input.required = true;
            wrap.appendChild(input);
            if (section.suffix) {
                const suffix = document.createElement('span');
                suffix.className   = 'flow-number__suffix';
                suffix.textContent = section.suffix;
                wrap.appendChild(suffix);
            }
            group.appendChild(wrap);
        } else {
            const input = document.createElement('input');
            input.type = 'text';
            input.id   = section.id;
            input.name = section.id;
            if (section.required) input.required = true;
            group.appendChild(input);
        }

        return group;
    }

    // Card grid (display_hint: "cards")
    function renderCardGroup(section) {
        const grid = document.createElement('div');
        grid.className = 'question-card-grid';

        section.options.forEach(opt => {
            const card = document.createElement('div');
            card.className   = 'question-card';
            card.dataset.value = opt.value;

            // Hidden radio
            const radio = document.createElement('input');
            radio.type  = 'radio';
            radio.name  = section.id;
            radio.value = opt.value;
            radio.id    = `${section.id}_${opt.id}`;
            if (section.required) radio.required = true;
            card.appendChild(radio);

            // Radio indicator dot
            const dot = document.createElement('div');
            dot.className = 'question-card__radio';
            card.appendChild(dot);

            // Icon
            const icon = document.createElement('div');
            icon.className = 'question-card__icon';
            icon.innerHTML = getCardIcon(section.id, opt.id);
            card.appendChild(icon);

            // Title
            const title = document.createElement('div');
            title.className   = 'question-card__title';
            title.textContent = opt.label;
            card.appendChild(title);

            // Click handler
            card.addEventListener('click', () => {
                grid.querySelectorAll('.question-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                radio.checked = true;
            });

            grid.appendChild(card);
        });

        return grid;
    }

    // Multi-select card grid (display_hint: "cards" on a multi_select).
    // Optional `section.max` caps the number of simultaneously selected cards.
    function renderMultiCardGroup(section) {
        const grid = document.createElement('div');
        grid.className = 'question-card-grid';
        // A section without `max` is unlimited; an EXPLICIT 0 (budget
        // exhausted) allows no further selections. Never treat 0 as
        // unlimited — that bypass let 2 regions + 2 themes through at
        // BALANCED budget 2 (port_20260903_12e34942).
        const hasMax = section.max != null;
        const max = hasMax ? Number(section.max) : 0;

        section.options.forEach(opt => {
            const card = document.createElement('div');
            card.className   = 'question-card';
            card.dataset.value = opt.value;

            const cb = document.createElement('input');
            cb.type  = 'checkbox';
            cb.name  = section.id;
            cb.value = opt.value;
            cb.id    = `${section.id}_${opt.id}`;
            card.appendChild(cb);

            const dot = document.createElement('div');
            dot.className = 'question-card__check';
            card.appendChild(dot);

            const icon = document.createElement('div');
            icon.className = 'question-card__icon';
            icon.innerHTML = getCardIcon(section.id, opt.id);
            card.appendChild(icon);

            const title = document.createElement('div');
            title.className   = 'question-card__title';
            title.textContent = opt.label;
            card.appendChild(title);

            // Feasibility-gated: no fund backing this option under the live
            // answers — render disabled-with-reason, never interactive.
            if (opt.gated_unavailable) {
                card.classList.add('question-card--disabled');
                card.title = gatedReasonText(opt);
                card.setAttribute('aria-disabled', 'true');
                cb.disabled = true;
                grid.appendChild(card);
                return;
            }

            card.addEventListener('click', () => {
                const isSelected = card.classList.contains('selected');
                if (!isSelected && hasMax) {
                    const count = grid.querySelectorAll('.question-card.selected').length;
                    if (count >= max) {
                        showFlowError(
                            t('errors.flow_max_selection', 'You can select up to {max} options.')
                                .replace('{max}', max)
                        );
                        return;
                    }
                }
                clearFlowError();
                card.classList.toggle('selected');
                cb.checked = card.classList.contains('selected');
            });

            grid.appendChild(card);
        });

        return grid;
    }

    // Chip grid (display_hint: "chips")
    function renderChipGroup(section) {
        const wrap = document.createElement('div');
        wrap.className = 'chip-grid';

        const isMulti = section.type === 'multi_select';
        // Explicit `max: 0` (budget exhausted) blocks all selections;
        // only an absent `max` means unlimited (see renderMultiCardGroup).
        const hasMax = section.max != null;
        const max = hasMax ? Number(section.max) : 0;

        // Options flagged selectable:false (e.g. the theme "none" default) are
        // valid values but not offered as chips.
        section.options.filter(opt => opt.selectable !== false).forEach(opt => {
            const chip = document.createElement('div');
            chip.className = 'chip';
            chip.dataset.value = opt.value;

            // Checkmark SVG
            chip.innerHTML = `
                <svg class="chip__check" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="2,8 6,12 14,4"/>
                </svg>
                <span>${opt.label}</span>
            `;

            // Hidden input
            const input = document.createElement('input');
            input.type  = isMulti ? 'checkbox' : 'radio';
            input.name  = section.id;
            input.value = opt.value;
            input.id    = `${section.id}_${opt.id}`;
            chip.appendChild(input);

            // Feasibility-gated: no fund backing this option under the live
            // answers — render disabled-with-reason, never interactive.
            if (opt.gated_unavailable) {
                chip.classList.add('chip--disabled');
                chip.title = gatedReasonText(opt);
                chip.setAttribute('aria-disabled', 'true');
                input.disabled = true;
                wrap.appendChild(chip);
                return;
            }

            chip.addEventListener('click', () => {
                if (isMulti) {
                    const willSelect = !chip.classList.contains('selected');
                    if (willSelect && hasMax) {
                        const count = wrap.querySelectorAll('.chip.selected').length;
                        if (count >= max) {
                            showFlowError(
                                t('errors.flow_max_selection', 'You can select up to {max} options.')
                                    .replace('{max}', max)
                            );
                            return;
                        }
                    }
                    clearFlowError();
                    chip.classList.toggle('selected');
                    input.checked = chip.classList.contains('selected');
                } else {
                    wrap.querySelectorAll('.chip').forEach(c => {
                        c.classList.remove('selected');
                        c.querySelector('input').checked = false;
                    });
                    chip.classList.add('selected');
                    input.checked = true;
                }
            });

            wrap.appendChild(chip);
        });

        return wrap;
    }

    // Standard <select> dropdown
    function renderSelectField(section) {
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';

        const select = document.createElement('select');
        select.id   = section.id;
        select.name = section.id;
        if (section.required) select.required = true;

        const defaultOpt = document.createElement('option');
        defaultOpt.value    = '';
        defaultOpt.textContent = t('ui.select_placeholder', 'Select an option...');
        defaultOpt.disabled = true;
        defaultOpt.selected = true;
        select.appendChild(defaultOpt);

        section.options.forEach(opt => {
            const option = document.createElement('option');
            option.value       = opt.value;
            option.textContent = opt.label;
            select.appendChild(option);
        });

        wrapper.appendChild(select);
        return wrapper;
    }

    // Checkbox list
    function renderCheckboxList(section) {
        const list = document.createElement('div');
        list.className = 'checkbox-list';

        section.options.forEach(opt => {
            const label = document.createElement('label');
            label.className = 'checkbox-item';

            const cb = document.createElement('input');
            cb.type  = 'checkbox';
            cb.name  = section.id;
            cb.value = opt.value;
            cb.id    = `${section.id}_${opt.id}`;

            label.appendChild(cb);
            label.appendChild(document.createTextNode(opt.label));
            list.appendChild(label);
        });

        return list;
    }

    // Icons for card questions — inline SVG keyed by section + option ID
    function getCardIcon(sectionId, optId) {
        const icons = {
            // Risk approach — gauge / speedometer style
            'risk_approach_conservative': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 38a20 20 0 0136 0"/><line x1="28" y1="38" x2="16" y2="24"/><circle cx="28" cy="38" r="2.5" fill="currentColor"/></svg>`,
            'risk_approach_moderate_low': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 38a20 20 0 0136 0"/><line x1="28" y1="38" x2="22" y2="20"/><circle cx="28" cy="38" r="2.5" fill="currentColor"/></svg>`,
            'risk_approach_moderate':     `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 38a20 20 0 0136 0"/><line x1="28" y1="38" x2="28" y2="18"/><circle cx="28" cy="38" r="2.5" fill="currentColor"/></svg>`,
            'risk_approach_aggressive':   `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 38a20 20 0 0136 0"/><line x1="28" y1="38" x2="40" y2="22"/><circle cx="28" cy="38" r="2.5" fill="currentColor"/></svg>`,

            // (loss_tolerance removed)

            // ESG
            'esg_none':            `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="28" cy="28" r="16"/><line x1="16" y1="16" x2="40" y2="40"/></svg>`,
            'esg_prefer':          `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M28 14c-6 8-10 14-10 20a10 10 0 0020 0c0-6-4-12-10-20z"/></svg>`,
            'esg_only':            `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M28 12c-8 10-14 18-14 22a14 14 0 0028 0c0-4-6-12-14-22z"/><line x1="28" y1="42" x2="28" y2="30"/></svg>`,

            // ETF preference
            'no_etf_preference': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="12" y="20" width="10" height="18" rx="1"/><rect x="24" y="14" width="10" height="24" rx="1"/><rect x="36" y="24" width="10" height="14" rx="1"/></svg>`,
            'prefer_etf':        `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 28h8l6-10 8 20 6-14 6 4"/></svg>`,
            'etf_only':          `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="28" cy="28" r="14"/><polyline points="22,28 26,32 35,22"/></svg>`,

            // Investment goal
            'wealth_building': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="12,38 22,26 30,32 44,18"/><polyline points="36,18 44,18 44,26"/></svg>`,
            'retirement':      `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="28" cy="22" r="8"/><path d="M16 42v-2a12 12 0 0124 0v2"/></svg>`,
            'home_ownership':  `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 28l16-14 16 14v16H12z"/><rect x="22" y="32" width="12" height="12"/></svg>`,
            'wealth_transfer': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 28h6l4-8 4 16 4-10 4 4 4-2"/></svg>`,

            // Investment knowledge
            'confident': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16,28 24,36 40,20"/></svg>`,
            'beginner':  `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="28" cy="24" r="6"/><line x1="28" y1="32" x2="28" y2="42"/><line x1="22" y1="36" x2="34" y2="36"/></svg>`,
        };
        return icons[`${sectionId}_${optId}`]
            || icons[optId]
            || `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2"><circle cx="28" cy="28" r="14"/></svg>`;
    }

    // -------------------------------------------------------------------------
    // Form submission
    // -------------------------------------------------------------------------
    async function handleSubmission(e) {
        e.preventDefault();
        errorView.classList.add('hidden');
        clearResults();
        setLoadingState(true);

        const userAnswers = gatherAnswers(qForm);

        const payload = { user_answers: userAnswers, language: currentLang };
        if (currentPortfolioId) payload.portfolio_id = currentPortfolioId;

        console.log('Submitting payload:', payload);

        try {
            const response = await fetch('/api/portfolio', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            });

            const data = await response.json();
            if (!response.ok) {
                const details = data.details?.length ? `\nReason: ${data.details.join('; ')}` : '';
                throw new Error((data.error || 'Failed to generate portfolio') + details);
            }

            renderResults(data, { showTraces: showTracesForMode });
        } catch (err) {
            showError(err.message);
            setLoadingState(false);
        }
    }

    // -------------------------------------------------------------------------
    // Shared result component (see MODES.md §2)
    //
    // Single entry point used by every UI mode. `showTraces` controls the
    // technical decision-trace block only:
    //   true  → Quick-Mode (full traces)
    //   false → Flow-Mode (end-user friendly; summary + answers still shown)
    // Reads only the response fields documented in MODES.md §1.
    // -------------------------------------------------------------------------
    function renderResults(portfolio, { showTraces = true } = {}) {
        setLoadingState(false);
        formView.classList.add('hidden');
        resultsView.classList.remove('hidden');

        // Portfolio ID
        if (displayPortId) {
            displayPortId.textContent = portfolio.portfolio_id || t('ui.unknown_id', 'Unknown ID');
        }

        // Risk profile — translated display name
        const riskRaw   = portfolio.risk_profile || portfolio.user_answers?.risk_approach || '';
        const riskLabel = t(`ui.risk_profile_${riskRaw.toLowerCase()}`, riskRaw.replace(/_/g, ' ').toUpperCase());
        if (scoreVal) scoreVal.textContent = riskLabel;

        // Weighted fee
        if (weightedFeeVal) {
            const fee = portfolio.portfolio_metrics?.weighted_fee
                ?? portfolio.calculated_metrics?.weighted_fee
                ?? portfolio.weighted_fee;
            weightedFeeVal.textContent = fee != null ? `${Number(fee).toFixed(3)}%` : '—';
        }

        // Preference-satisfaction summary (single source of truth:
        // portfolio.portfolio_metrics.preference_satisfaction, computed by the engine).
        renderPreferenceSatisfaction(portfolio);

        // Decision summary (Preferences tab)
        if (decisionSummaryText) {
            decisionSummaryText.textContent =
                portfolio.explanations?.summary || t('ui.summary_unavailable');
        }

        if (decisionFilters) {
            decisionFilters.innerHTML = '';
            decisionFilters.classList.toggle('hidden', !showTraces);
            if (showTraces) {
                (portfolio.decision_trace?.filters || []).forEach(f => {
                    decisionFilters.appendChild(makeFilterPill(`${f.name}: ${f.before}→${f.after}`));
                });
                (portfolio.decision_trace?.relaxations || []).forEach(r => {
                    const label = r.reason ? `${r.name}: ${r.reason}` : `relaxation: ${r.name} ${r.before}→${r.after}`;
                    decisionFilters.appendChild(makeFilterPill(label));
                });
            }
        }

        renderDecisionTrace(portfolio.decision_trace, showTraces);

        // Render user answers as filter pills (same styling as decision-filters)
        if (userAnswersFilters) {
            userAnswersFilters.innerHTML = '';
            const answers = portfolio.user_answers || {};
            Object.entries(answers).forEach(([key, value]) => {
                const displayValue = Array.isArray(value) ? value.join(', ') : String(value);
                userAnswersFilters.appendChild(makeFilterPill(`${key}: ${displayValue}`));
            });
        }

        if (!portfolio.recommendations?.length) {
            const tbody = fundTableBody;
            if (tbody) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 5;
                td.style.textAlign = 'center';
                td.style.padding = '2rem';
                td.style.color = 'var(--md-sys-color-on-surface-variant)';
                td.textContent = t('ui.no_recommendations');
                tr.appendChild(td);
                tbody.appendChild(tr);
            }
            return;
        }

        renderFundTable(portfolio.recommendations);

        // Persist for Phase-2 tabs
        lastPortfolio       = portfolio;
        currentPortfolioId  = portfolio.portfolio_id || currentPortfolioId;

        if (fundCount) {
            fundCount.textContent = `(${portfolio.recommendations.length})`;
        }

        // Summary breakdowns (donuts + text summary)
        renderBreakdowns(portfolio).catch(err => console.warn('breakdowns failed', err));

        // Switch to summary tab on fresh results
        const summaryTabBtn = document.querySelector('[data-tab="tab-summary"]');
        if (summaryTabBtn) switchTab(summaryTabBtn);
    }

    // -------------------------------------------------------------------------
    // Phase 2 — breakdowns, performance, volatility
    // -------------------------------------------------------------------------
    async function fetchJson(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url} → ${res.status}`);
        return res.json();
    }

    function aggregateBreakdownLocally(portfolio) {
        // Fallback used when the portfolio_id-based endpoint isn't reachable
        const asset = {};
        const region = {};
        let totalWeight = 0;
        (portfolio.recommendations || []).forEach(rec => {
            const w = (rec.allocation_percent || 0) / 100;
            if (w <= 0) return;
            totalWeight += w;
            const ac = rec.asset_class_breakdown;
            if (ac && Object.keys(ac).length) {
                Object.entries(ac).forEach(([k, v]) => {
                    asset[k] = (asset[k] || 0) + w * (v || 0);
                });
            } else {
                const k = (rec.asset_class || 'other').toLowerCase();
                asset[k] = (asset[k] || 0) + w;
            }
            const rb = rec.region_breakdown;
            if (rb && Object.keys(rb).length) {
                Object.entries(rb).forEach(([k, v]) => {
                    region[k] = (region[k] || 0) + w * (v || 0);
                });
            } else {
                const k = (rec.region || 'unknown').toLowerCase();
                region[k] = (region[k] || 0) + w;
            }
        });
        const norm = (m) => totalWeight > 0
            ? Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v / totalWeight]))
            : m;
        return { asset_class: norm(asset), region: norm(region) };
    }

    async function renderBreakdowns(portfolio) {
        let breakdown;
        if (portfolio.portfolio_id) {
            try {
                const resp = await fetchJson(`/api/portfolio/${portfolio.portfolio_id}/breakdown`);
                breakdown = resp.breakdown;
            } catch (err) {
                console.warn('breakdown endpoint failed, computing locally:', err);
            }
        }
        if (!breakdown) breakdown = aggregateBreakdownLocally(portfolio);

        await window.FundsCharts.ensureChartJs();

        const acEntries = Object.entries(breakdown.asset_class || {}).sort((a, b) => b[1] - a[1]);
        const rEntries  = Object.entries(breakdown.region      || {}).sort((a, b) => b[1] - a[1]);

        const acLabel = (k) => t(`ui.asset_class_${k}`, k);
        const rLabel  = (k) => t(`ui.region_${k}`,      k.replace(/_/g, ' '));

        window.FundsCharts.renderBreakdownDonut('chart-asset-classes', {
            labels: acEntries.map(([k]) => k),
            values: acEntries.map(([, v]) => v),
            legendId: 'chart-asset-classes-legend',
            formatLabel: acLabel,
        });
        window.FundsCharts.renderBreakdownDonut('chart-regions', {
            labels: rEntries.map(([k]) => k),
            values: rEntries.map(([, v]) => v),
            legendId: 'chart-regions-legend',
            formatLabel: rLabel,
        });

    }

    async function ensureStressPeriodsLoaded() {
        if (stressPeriodsCfg) return stressPeriodsCfg;
        try {
            const data = await fetchJson('/api/config/stress-periods');
            stressPeriodsCfg = data.stress_periods || [];
        } catch (err) {
            console.warn('stress-periods config failed:', err);
            stressPeriodsCfg = [];
        }
        stressPeriodsCfg.forEach(p => {
            if (stressEnabled[p.id] === undefined) {
                stressEnabled[p.id] = !!p.enabled_by_default;
            }
        });
        return stressPeriodsCfg;
    }

    function renderStressToggles() {
        const host = document.getElementById('stress-overlay-toggles');
        if (!host) return;
        host.innerHTML = '';
        (stressPeriodsCfg || []).forEach(p => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'stress-toggle' + (stressEnabled[p.id] ? ' active' : '');
            btn.dataset.id = p.id;
            const label = t(p.i18n_key, p.id);
            btn.innerHTML = `<span class="stress-swatch" style="background:${p.color || '#E53935'}"></span>${escHtml(label)}`;
            btn.addEventListener('click', () => {
                stressEnabled[p.id] = !stressEnabled[p.id];
                btn.classList.toggle('active', stressEnabled[p.id]);
                renderPerformanceTab().catch(err => console.warn(err));
            });
            host.appendChild(btn);
        });
    }

    function bindPerfPeriodSelector() {
        document.querySelectorAll('.perf-period').forEach(btn => {
            if (btn.dataset._bound) return;
            btn.dataset._bound = '1';
            btn.addEventListener('click', () => {
                selectedPerfPeriod = btn.dataset.period || '10y';
                document.querySelectorAll('.perf-period').forEach(b => b.classList.toggle('active', b === btn));
                renderPerformanceTab().catch(err => console.warn(err));
            });
        });
    }

    function periodToRange(period) {
        const now  = new Date();
        const iso  = (d) => d.toISOString().slice(0, 10);
        const yrs = { '1y': 1, '3y': 3, '5y': 5, '10y': 10 };
        if (yrs[period]) {
            const from = new Date(now.getFullYear() - yrs[period], now.getMonth(), now.getDate());
            return { from: iso(from), to: iso(now) };
        }
        return { from: null, to: null }; // since inception
    }

    async function renderPerformanceTab() {
        const myToken = ++perfFetchToken;
        await window.FundsCharts.ensureChartJs();
        await ensureStressPeriodsLoaded();
        renderStressToggles();
        bindPerfPeriodSelector();

        const notes = document.getElementById('performance-notes');
        const tbody = document.getElementById('returns-table-body');

        if (!lastPortfolio || !lastPortfolio.portfolio_id) {
            if (notes) notes.textContent = t('ui.no_portfolio_loaded', 'No portfolio loaded.');
            return;
        }

        const { from, to } = periodToRange(selectedPerfPeriod);
        const qs = from && to ? `?from=${from}&to=${to}` : '';
        let perf;
        try {
            perf = await fetchJson(`/api/portfolio/${lastPortfolio.portfolio_id}/performance${qs}`);
        } catch (err) {
            if (myToken !== perfFetchToken) return;
            if (notes) notes.textContent = t('ui.no_data_available', 'No data available.');
            window.FundsCharts.renderPerformanceChart('chart-performance', { portfolio: [], benchmark: null, stressBands: [] });
            if (tbody) tbody.innerHTML = '';
            return;
        }
        if (myToken !== perfFetchToken) return;

        const stressBands = (stressPeriodsCfg || []).map(p => ({
            id: p.id,
            start: p.start,
            end: p.end,
            color: p.color,
            label: t(p.i18n_key, p.id),
            enabled: !!stressEnabled[p.id],
        }));

        const fundSeries = perf.fund_series || [];

        window.FundsCharts.renderPerformanceChart('chart-performance', {
            portfolio: perf.portfolio_series || [],
            funds: fundSeries,
            benchmark: perf.benchmark
                ? { series: perf.benchmark_series || [], label: perf.benchmark.name || t('ui.benchmark', 'Benchmark') }
                : null,
            stressBands,
            labels: { portfolio: t('ui.portfolio', 'Portfolio'), benchmark: t('ui.benchmark', 'Benchmark') },
        });

        // Per-fund on/off chips — toggle each fund dataset's visibility.
        renderFundToggles(fundSeries);

        if (notes) {
            const parts = [];
            if ((perf.notes || []).includes('clipped_to_shortest_history')) {
                parts.push(t('ui.note_clipped_history', 'Some funds have shorter history; portfolio line uses the common window.'));
            }
            if ((perf.excluded_isins || []).length) {
                parts.push(t('ui.note_excluded_funds', 'Excluded (no data in range): ') + perf.excluded_isins.join(', '));
            }
            if ((perf.portfolio_series || []).length === 0) {
                parts.push(t('ui.no_data_available', 'No data available.'));
            }
            notes.textContent = parts.join(' ');
        }

        await renderReturnsTable();
    }

    async function renderReturnsTable() {
        const tbody = document.getElementById('returns-table-body');
        if (!tbody || !lastPortfolio?.recommendations?.length) return;
        tbody.innerHTML = '';

        const fmtPct = (v) => {
            if (v == null) return `<span class="return-na">n/a</span>`;
            const num = Number(v);
            const cls = num >= 0 ? 'return-pos' : 'return-neg';
            return `<span class="${cls}">${(num * 100).toFixed(2)}%</span>`;
        };

        await Promise.all(lastPortfolio.recommendations.map(async (rec) => {
            const tr = document.createElement('tr');
            let perf = null;
            try {
                const resp = await fetchJson(`/api/funds/${rec.isin}/performance`);
                perf = resp.performance;
            } catch (e) { /* missing → n/a */ }
            const periods = (perf && perf.periods) || {};
            tr.innerHTML = `
                <td>${escHtml(rec.name || rec.isin)}</td>
                <td>${fmtPct(periods['3m'])}</td>
                <td>${fmtPct(periods['1y'])}</td>
                <td>${fmtPct(periods['3y_pa'])}</td>
                <td>${fmtPct(periods['5y_pa'])}</td>
                <td>${fmtPct(periods['si_pa'])}</td>
            `;
            tbody.appendChild(tr);
        }));
    }

    async function renderVolatilityTab() {
        const myToken = ++volFetchToken;
        await window.FundsCharts.ensureChartJs();

        const tbody = document.getElementById('risk-table-body');
        if (!lastPortfolio?.recommendations?.length) {
            window.FundsCharts.renderVolatilityChart('chart-volatility', { rows: [] });
            if (tbody) tbody.innerHTML = '';
            return;
        }

        const rows = await Promise.all(lastPortfolio.recommendations.map(async (rec) => {
            let risk = null;
            try {
                risk = await fetchJson(`/api/funds/${rec.isin}/risk`);
            } catch (e) { /* missing */ }
            const vol = (risk && risk.volatility) || {};
            const rm  = (risk && risk.risk_metrics) || {};
            return {
                isin: rec.isin,
                name: (rec.name || rec.isin).split(' ').slice(0, 4).join(' '),
                vol_1y: vol['1y'] ?? null,
                vol_3y: vol['3y'] ?? null,
                vol_5y: vol['5y'] ?? null,
                sharpe_3y: (rm.sharpe || {})['3y'] ?? null,
                mdd_3y:    (rm.max_drawdown || {})['3y'] ?? null,
            };
        }));
        if (myToken !== volFetchToken) return;

        window.FundsCharts.renderVolatilityChart('chart-volatility', {
            rows,
            labels: {
                vol_1y: t('ui.vol_1y', 'Vol 1Y'),
                vol_3y: t('ui.vol_3y', 'Vol 3Y'),
                vol_5y: t('ui.vol_5y', 'Vol 5Y'),
            },
        });

        if (tbody) {
            tbody.innerHTML = '';
            const fmtPct = (v) => v == null
                ? `<span class="return-na">n/a</span>`
                : `${(v * 100).toFixed(2)}%`;
            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${escHtml(r.name)}</td>
                    <td>${fmtPct(r.vol_1y)}</td>
                    <td>${fmtPct(r.vol_3y)}</td>
                    <td>${fmtPct(r.vol_5y)}</td>
                    <td>${r.sharpe_3y == null ? '<span class="return-na">n/a</span>' : r.sharpe_3y.toFixed(2)}</td>
                    <td>${r.mdd_3y == null ? '<span class="return-na">n/a</span>' : `<span class="return-neg">${(r.mdd_3y * 100).toFixed(1)}%</span>`}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    }

    // -------------------------------------------------------------------------
    // Fund table
    // -------------------------------------------------------------------------
    function renderFundTable(recommendations) {
        if (!fundTableBody) return;
        fundTableBody.innerHTML = '';

        recommendations.forEach((rec, idx) => {
            const stars    = scoreToStars(rec.quality_score);
            const assetCls = (rec.asset_class || 'other').toLowerCase();
            const badgeCls = { equity: 'badge--equity', bond: 'badge--bond', mixed: 'badge--mixed' }[assetCls] || '';
            const assetLabel = t(`ui.asset_class_${assetCls}`, rec.asset_class || '—');

            // Main row
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <div class="fund-name">${escHtml(rec.name || 'Unknown Fund')}</div>
                    <div class="fund-isin">${escHtml(rec.isin || 'N/A')}</div>
                </td>
                <td><span class="star-rating" title="${t('ui.detail_quality_score', 'Quality score')}: ${rec.quality_score ?? '—'}">${stars}</span></td>
                <td><span class="badge ${badgeCls}">${escHtml(assetLabel)}</span></td>
                <td><span class="fund-alloc">${Math.round(rec.allocation_percent || 0)}%</span></td>
                <td>
                    <button class="fund-expand-btn" aria-expanded="false" aria-label="${t('ui.detail_show', 'Show details')}" data-idx="${idx}">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <polyline points="4,6 8,10 12,6"/>
                        </svg>
                    </button>
                </td>
            `;

            // Detail row (hidden)
            const detailTr = document.createElement('tr');
            detailTr.className = 'fund-detail-row hidden';

            const detailTd = document.createElement('td');
            detailTd.colSpan = 5;

            const feeStr       = rec.yearly_fee != null ? `${Number(rec.yearly_fee).toFixed(2)}%` : 'N/A';
            const coreSatBadge = rec.core_satellite_class
                ? `<span class="badge ${rec.core_satellite_class === 'satellite' ? 'badge--satellite' : 'badge--core'}">${t(`ui.class_${rec.core_satellite_class}`, rec.core_satellite_class)}</span> `
                : '';
            const etfBadge = rec.etf_not_available
                ? `<span class="badge badge--etf-fallback">${t('ui.badge_active_no_etf', 'active (no ETF)')}</span> `
                : '';

            const explanations = Array.isArray(rec.explanations) ? rec.explanations : [];
            const reasonItems  = explanations.map(e => `<li>${escHtml(e)}</li>`).join('');

            detailTd.innerHTML = `
                <div class="fund-detail-inner">
                    <div class="fund-detail-section">
                        <div class="fund-detail-section__title">${t('ui.detail_classification', 'Classification')}</div>
                        <div style="display:flex; flex-wrap:wrap; gap:0.4rem; margin-top:0.25rem;">
                            ${coreSatBadge}${etfBadge}
                            <span class="badge">${t('ui.detail_exp_ratio', 'Exp. ratio')}: ${feeStr}</span>
                        </div>
                    </div>
                    ${explanations.length ? `
                    <div class="fund-detail-section">
                        <div class="fund-detail-section__title">${t('ui.detail_why_selected', 'Why selected')}</div>
                        <ul class="fund-reason-list">${reasonItems}</ul>
                    </div>` : ''}
                </div>
            `;
            detailTr.appendChild(detailTd);

            // Expand toggle
            tr.querySelector('.fund-expand-btn').addEventListener('click', () => {
                const btn      = tr.querySelector('.fund-expand-btn');
                const isOpen   = btn.classList.contains('open');
                btn.classList.toggle('open', !isOpen);
                btn.setAttribute('aria-expanded', String(!isOpen));
                detailTr.classList.toggle('hidden', isOpen);
                syncExpandAllState();
            });

            fundTableBody.appendChild(tr);
            fundTableBody.appendChild(detailTr);
        });

        setExpandAllState(false);
    }

    // Reflect "expand all" state on the header button (label + chevron direction)
    function setExpandAllState(expand) {
        if (!expandAllBtn) return;
        expandAllBtn.classList.toggle('open', expand);
        expandAllBtn.setAttribute('aria-expanded', String(expand));
        const label = expand
            ? t('ui.collapse_all', 'Collapse all funds')
            : t('ui.expand_all',   'Expand all funds');
        expandAllBtn.setAttribute('aria-label', label);
        expandAllBtn.title = label;
    }

    // Sync header button after an individual row toggle: "open" only if every row is open
    function syncExpandAllState() {
        if (!expandAllBtn || !fundTableBody) return;
        const btns = fundTableBody.querySelectorAll('.fund-expand-btn');
        const allOpen = btns.length > 0 &&
            Array.from(btns).every(b => b.classList.contains('open'));
        setExpandAllState(allOpen);
    }

    // Convert quality_score (0–100) to ★★★★★ string
    function scoreToStars(score) {
        if (score == null) return '<span class="star-empty">★★★★★</span>';
        const filled = Math.round((score / 100) * 5);
        const empty  = 5 - filled;
        return '★'.repeat(filled) + `<span class="star-empty">${'★'.repeat(empty)}</span>`;
    }

    // -------------------------------------------------------------------------
    // Tab switching
    // -------------------------------------------------------------------------
    function switchTab(btn) {
        document.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const panel = document.getElementById(btn.dataset.tab);
        if (panel) panel.classList.add('active');

        const tabId = btn.dataset.tab;
        if (tabId === 'tab-perf') {
            renderPerformanceTab().catch(err => console.warn('perf tab render failed', err));
        } else if (tabId === 'tab-vol') {
            renderVolatilityTab().catch(err => console.warn('vol tab render failed', err));
        }
    }

    // -------------------------------------------------------------------------
    // Reset / clear
    // -------------------------------------------------------------------------
    function clearResults() {
        resultsView.classList.add('hidden');
        if (displayPortId)        displayPortId.textContent   = '';
        if (scoreVal)             scoreVal.textContent         = '';
        if (weightedFeeVal)       weightedFeeVal.textContent   = '—';
        if (assetClassLegend)     assetClassLegend.innerHTML    = '';
        if (regionLegend)         regionLegend.innerHTML       = '';
        if (fundCount)            fundCount.textContent        = '';
        if (decisionSummaryText)  decisionSummaryText.textContent = '';
        if (decisionFilters)      decisionFilters.innerHTML    = '';
        if (fundTableBody)        fundTableBody.innerHTML      = '';
        const returnsBody = document.getElementById('returns-table-body');
        const riskBody    = document.getElementById('risk-table-body');
        const perfNotes   = document.getElementById('performance-notes');
        if (returnsBody) returnsBody.innerHTML = '';
        if (riskBody)    riskBody.innerHTML    = '';
        if (perfNotes)   perfNotes.textContent = '';
        lastPortfolio = null;
    }

    function resetApp() {
        clearResults();
        errorView.classList.add('hidden');
        qForm.reset();
        // Reset card / chip selections
        document.querySelectorAll('.question-card.selected').forEach(c => c.classList.remove('selected'));
        document.querySelectorAll('.chip.selected').forEach(c => c.classList.remove('selected'));
        welcomeView.classList.remove('hidden');
        resumeIdInput.value = '';
        resumeError.classList.add('hidden');
        currentPortfolioId  = null;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // -------------------------------------------------------------------------
    // Resume portfolio
    // -------------------------------------------------------------------------
    async function handleResume(e) {
        e.preventDefault();
        resumeError.classList.add('hidden');

        let targetId = resumeIdInput.value.trim();
        if (!targetId) {
            resumeError.textContent = t('errors.resume_invalid');
            resumeError.classList.remove('hidden');
            return;
        }
        if (targetId.endsWith('.json'))      targetId = targetId.replace('.json', '');
        if (!targetId.startsWith('port_'))   targetId = 'port_' + targetId;

        try {
            const submitBtnEl = resumeForm.querySelector('button[type="submit"]');
            submitBtnEl.textContent = t('ui.locating', 'Locating...');
            submitBtnEl.disabled    = true;

            const response = await fetch(`/api/portfolio/${targetId}`);
            if (!response.ok) {
                throw new Error(response.status === 404
                    ? t('errors.resume_not_found')
                    : t('errors.resume_failed'));
            }

            const savedPortfolio       = await response.json();
            currentPortfolioId         = savedPortfolio.portfolio_id;
            activePortIdDisplay.textContent = currentPortfolioId;
            activeSessionBanner.classList.remove('hidden');
            showFormView(savedPortfolio.user_answers || {});
        } catch (err) {
            resumeError.textContent = err.message;
            resumeError.classList.remove('hidden');
        } finally {
            const submitBtnEl = resumeForm.querySelector('button[type="submit"]');
            submitBtnEl.textContent = t('ui.resume_button', 'Resume Portfolio');
            submitBtnEl.disabled    = false;
        }
    }

    function showFormView(prefillAnswers) {
        welcomeView.classList.add('hidden');
        formView.classList.remove('hidden');

        if (!currentPortfolioId) activeSessionBanner.classList.add('hidden');

        if (prefillAnswers && Object.keys(prefillAnswers).length > 0) {
            applyPrefill(qForm, prefillAnswers);
        }
    }

    // -------------------------------------------------------------------------
    // Shared input helpers — gather answers from / prefill answers into any
    // scope (the Quick-Mode <form> or a Flow-Mode wizard step container).
    // gatherAnswers mirrors FormData semantics: only checked radios/checkboxes
    // contribute, checkboxes group into arrays, empty values are dropped.
    // -------------------------------------------------------------------------
    function gatherAnswers(scope) {
        const answers        = {};
        const checkboxGroups = {};
        scope.querySelectorAll('input[name], select[name], textarea[name]').forEach(el => {
            const key = el.name;
            if (el.type === 'radio') {
                if (el.checked) answers[key] = el.value;
            } else if (el.type === 'checkbox') {
                if (el.checked) (checkboxGroups[key] = checkboxGroups[key] || []).push(el.value);
            } else if (el.value !== '') {
                answers[key] = el.value;
            }
        });
        Object.assign(answers, checkboxGroups);
        return answers;
    }

    function applyPrefill(scope, answers) {
        if (!answers) return;
        Object.entries(answers).forEach(([key, value]) => {
            const elements = scope.querySelectorAll(`[name="${key}"]`);
            if (!elements.length) return;

            if (elements[0].type === 'checkbox') {
                const arr = Array.isArray(value) ? value : [value];
                elements.forEach(cb => {
                    cb.checked = arr.includes(cb.value);
                    const card = cb.closest('.question-card');
                    if (card) card.classList.toggle('selected', cb.checked);
                    const chip = cb.closest('.chip');
                    if (chip) chip.classList.toggle('selected', cb.checked);
                });
            } else if (elements[0].type === 'radio') {
                elements.forEach(radio => {
                    radio.checked = radio.value === value;
                    const card = radio.closest('.question-card');
                    if (card) card.classList.toggle('selected', radio.checked);
                    const chip = radio.closest('.chip');
                    if (chip) chip.classList.toggle('selected', radio.checked);
                });
            } else if (elements[0].tagName.toLowerCase() === 'select') {
                const optExists = Array.from(elements[0].options).some(o => o.value === value);
                if (optExists) elements[0].value = value;
            } else {
                elements[0].value = value;
            }
        });
    }

    // -------------------------------------------------------------------------
    // Flow-Mode wizard (see MODES.md §3/§4)
    //
    // Linear, declarative wizard driven by flows/variant<X>.json. Each step
    // renders one or more fields (questionnaire sections or inline fields) via
    // the shared renderSection(); answers accumulate in flowAnswers across
    // steps. The final step maps them to the common input model and issues a
    // single POST /api/portfolio — the exact same call Quick-Mode makes.
    // -------------------------------------------------------------------------
    async function loadFlowConfig() {
        if (flowConfig) return flowConfig;
        const response = await fetch(`/flows/variant${flowVariant}.json`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Flow config variant${flowVariant} not found`);
        flowConfig = await response.json();
        return flowConfig;
    }

    // Resolve the section object(s) a step renders, as an array (a step may
    // hold several fields, e.g. the contribution step's two number inputs).
    //   source: "section" → look up by id in the loaded questionnaire (already localized)
    //   source: "inline"  → section/fields embedded in the step (localized here)
    function stepSections(step) {
        if (!step) return [];
        if (step.source === 'inline') {
            const raw = step.fields ? step.fields : (step.section ? [step.section] : []);
            return raw.map(localizeSection);
        }
        const sec = questionnaireSections.find(s => s.id === step.section);
        if (!sec) return [];
        // Per-step presentation overrides (e.g. render a chips section as cards
        // with a max limit in the flow) — clone so the shared section is intact.
        if (step.display_hint || step.max != null) {
            return [{
                ...sec,
                display_hint: step.display_hint || sec.display_hint,
                max: step.max != null ? step.max : sec.max,
            }];
        }
        return [sec];
    }

    // Pick a localized string from a {de,en} object (or pass a plain string through).
    function loc(val) {
        if (val && typeof val === 'object' && !Array.isArray(val)) {
            return val[currentLang] || val.en || val.de || Object.values(val)[0] || '';
        }
        return val;
    }

    function localizeSection(section) {
        return {
            ...section,
            name:        loc(section.name),
            title:       loc(section.title),
            description: loc(section.description),
            options:     (section.options || []).map(o => ({ ...o, label: loc(o.label) })),
        };
    }

    // Conditional visibility — a step may declare `showIf`, either a single
    // condition or { allOf: [conditions] }. A condition is { field, equals } or
    // { field, notEquals }, evaluated against accumulated answers. Steps whose
    // condition fails are skipped during navigation (and dropped from progress).
    function evalCond(c) {
        const v = flowAnswers[c.field];
        if ('equals' in c)    return v === c.equals;
        if ('notEquals' in c) return v !== c.notEquals;
        return true;
    }
    function stepVisible(step) {
        const cond = step && step.showIf;
        if (!cond) return true;
        if (Array.isArray(cond.allOf)) return cond.allOf.every(evalCond);
        return evalCond(cond);
    }
    function visibleSteps() {
        return (flowConfig.steps || []).filter(stepVisible);
    }
    function nextVisibleIndex(from) {
        const steps = flowConfig.steps || [];
        for (let i = from + 1; i < steps.length; i++) if (stepVisible(steps[i])) return i;
        return -1;
    }
    function prevVisibleIndex(from) {
        const steps = flowConfig.steps || [];
        for (let i = from - 1; i >= 0; i--) if (stepVisible(steps[i])) return i;
        return -1;
    }

    async function showFlowView() {
        // Reveal the wizard shell first so any config-load error is visible
        // inside it (showError targets a node inside the hidden form-view).
        welcomeView.classList.add('hidden');
        formView.classList.add('hidden');
        resultsView.classList.add('hidden');
        flowView.classList.remove('hidden');
        flowStepHost.innerHTML = '';
        clearFlowError();

        try {
            await loadFlowConfig();
        } catch (err) {
            showFlowError(err.message);
            return;
        }
        flowAnswers   = {};
        flowStepIndex = Math.max(0, nextVisibleIndex(-1));
        renderFlowStep();
    }

    function renderFlowStep() {
        const steps = flowConfig.steps || [];
        const step  = steps[flowStepIndex];
        // Field-level visibility: within a step, fields with an unmet `showIf`
        // are hidden (e.g. only the relevant contribution field per payment mode).
        const sections = stepSections(step).filter(stepVisible);

        flowStepHost.innerHTML = '';
        clearFlowError();
        sections.forEach(section => flowStepHost.appendChild(renderSection(section)));
        applyPrefill(flowStepHost, flowAnswers);
        // Back-navigation may have invalidated earlier theme selections
        // under a changed risk approach — drop them and tell the user.
        pruneInfeasibleSelections(sections);

        // Progress — counts only currently-visible steps
        const vis   = visibleSteps();
        const total = vis.length;
        const pos   = vis.indexOf(step) + 1;
        const pct   = total ? Math.round((pos / total) * 100) : 0;
        if (flowProgressFill)  flowProgressFill.style.width = pct + '%';
        if (flowProgressLabel) {
            flowProgressLabel.textContent =
                `${t('ui.flow_step', 'Step')} ${pos} / ${total}`;
        }

        setFlowNavLabel();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Whether the current step is the last visible one (→ "Generate" vs "Next").
    // Recomputed live because the deciding answer (e.g. Komfort vs Aktiv) is
    // chosen on the very step whose lookahead it governs.
    function setFlowNavLabel() {
        if (!flowNextBtn) return;
        const isLast = nextVisibleIndex(flowStepIndex) === -1;
        flowNextBtn.textContent = isLast
            ? t('ui.generate_portfolio', 'Generate Portfolio')
            : t('ui.next', 'Next');
    }

    // Re-sync answers + nav label whenever the user changes a selection on the
    // current step (card/chip clicks set inputs programmatically, so we listen
    // on the host rather than relying on native change events alone).
    function onFlowStepInteract() {
        if (!flowConfig || flowView.classList.contains('hidden')) return;
        persistCurrentStep();
        setFlowNavLabel();
    }

    // Persist the current step's inputs into flowAnswers. Clears the keys this
    // step owns first, so deselecting (e.g. unchecking all chips) is honoured.
    function persistCurrentStep() {
        const owned = new Set(
            Array.from(flowStepHost.querySelectorAll('[name]')).map(el => el.name)
        );
        owned.forEach(key => delete flowAnswers[key]);
        Object.assign(flowAnswers, gatherAnswers(flowStepHost));
    }

    function currentStepValid() {
        return stepSections(flowConfig.steps[flowStepIndex]).every(section => {
            if (!section.required) return true;
            const value = flowAnswers[section.id];
            if (section.type === 'multi_select') return Array.isArray(value) && value.length > 0;
            return value != null && value !== '';
        });
    }

    function flowNext() {
        persistCurrentStep();
        if (!currentStepValid()) {
            showFlowError(t('errors.flow_select_option', 'Please choose an option to continue.'));
            return;
        }
        const next = nextVisibleIndex(flowStepIndex);
        if (next === -1) {
            finalizeFlow();
            return;
        }
        flowStepIndex = next;
        renderFlowStep();
    }

    function flowBack() {
        persistCurrentStep();
        const prev = prevVisibleIndex(flowStepIndex);
        if (prev === -1) {
            flowView.classList.add('hidden');
            welcomeView.classList.remove('hidden');
            return;
        }
        flowStepIndex = prev;
        renderFlowStep();
    }

    // Map accumulated flow answers to the common input model (MODES.md §1).
    // Logic-relevant steps use questionnaire sections, so their keys already
    // match the schema (risk_approach, esg_preference, …). Commercial inline
    // fields (anlageziel, beitrag, produkt, …) pass through unchanged: the
    // engine ignores unknown keys, but they are persisted with the portfolio
    // for documentation (the "send extras" decision). No region/theme Ja-Nein
    // adapter is needed — variant A reuses the multi-select sections directly.
    function mapFlowToUserAnswers(answers) {
        // Drop answers owned by currently-hidden steps so a Komfort skip or a
        // "Nein" gate doesn't leak stale region/theme selections from earlier
        // back-navigation. Everything else (logic keys + extras) passes through.
        const hidden = new Set();
        (flowConfig.steps || [])
            .filter(step => !stepVisible(step))
            .forEach(step => stepSections(step).forEach(s => hidden.add(s.id)));
        const out = {};
        Object.entries(answers).forEach(([k, v]) => { if (!hidden.has(k)) out[k] = v; });
        return out;
    }

    // Defensive net at the flow boundary: never send theme/region selections
    // the current answers render infeasible (stale resume data, races).
    // The server independently logs soft warnings for direct API callers.
    function filterInfeasiblePreferences(answers) {
        const profile = gatingProfile();
        if (!profile) return answers;
        const combo = liveComboKey();
        const fields = (budgetConfig() && budgetConfig().fields) || [];
        if (!fields.length) return answers;
        const out = { ...answers };
        fields.forEach(field => {
            const sec = questionnaireSections.find(s => s.id === field);
            const values = out[field];
            if (!sec || !Array.isArray(values) || !values.length) return;
            const unavailable = new Set(
                (sec.options || [])
                    .filter(opt => {
                        const per = (opt.feasible || {})[profile];
                        return per && per[combo] != null && per[combo] <= 0;
                    })
                    .map(opt => String(opt.value).toUpperCase())
            );
            const filtered = values.filter(v => !unavailable.has(String(v).toUpperCase()));
            if (filtered.length !== values.length) out[field] = filtered;
        });
        return out;
    }

    async function finalizeFlow() {
        if (flowNextBtn) flowNextBtn.disabled = true;
        const payload = {
            user_answers: filterInfeasiblePreferences(mapFlowToUserAnswers(flowAnswers)),
            language: currentLang,
        };
        if (currentPortfolioId) payload.portfolio_id = currentPortfolioId;

        try {
            const response = await fetch('/api/portfolio', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) {
                const details = data.details?.length ? `\nReason: ${data.details.join('; ')}` : '';
                throw new Error((data.error || 'Failed to generate portfolio') + details);
            }
            flowView.classList.add('hidden');
            renderResults(data, { showTraces: false });
        } catch (err) {
            showFlowError(err.message);
        } finally {
            if (flowNextBtn) flowNextBtn.disabled = false;
        }
    }

    function showFlowError(msg) {
        let box = document.getElementById('flow-error');
        if (!box) return;
        box.textContent = msg;
        box.classList.remove('hidden');
    }

    function clearFlowError() {
        const box = document.getElementById('flow-error');
        if (box) box.classList.add('hidden');
    }

    // -------------------------------------------------------------------------
    // UI helpers
    // -------------------------------------------------------------------------
    function setLoadingState(isLoading) {
        submitBtn.disabled = isLoading;
        if (isLoading) {
            btnText.textContent = t('ui.analyzing', 'Analyzing...');
            btnSpinner.classList.remove('hidden');
        } else {
            btnText.textContent = t('ui.generate_portfolio', 'Generate Portfolio');
            btnSpinner.classList.add('hidden');
        }
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorView.classList.remove('hidden');
    }

    function makeFilterPill(text) {
        const span = document.createElement('span');
        span.className   = 'decision-filter';
        span.textContent = text;
        return span;
    }

    // -------------------------------------------------------------------------
    // Deep decision trace (Quick-Mode only — see MODES.md §1/§2)
    // Renders the ranking/scoring, selection adjustments and allocation
    // breakdown. Hidden in Flow-Mode (showTraces=false).
    // -------------------------------------------------------------------------
    // Statuses of the two-pass selection. The trace UI only ever renders fresh
    // engine responses (the resume path prefills answers, it does not replay a
    // stored trace), so legacy pre-rework statuses are not needed here.
    const TRACE_STATUS = {
        selected:                 { key: 'ui.trace_status_selected',  fallback: 'Selected',            cls: 'trace-status--ok' },
        selected_pass1_coverage:  { key: 'ui.trace_status_pass1',     fallback: 'Selected (1) · {dims} match', cls: 'trace-status--ok' },
        skipped_provider_cap:     { key: 'ui.trace_status_provider',  fallback: 'Skipped · provider cap', cls: 'trace-status--skip' },
        skipped_category_cap:     { key: 'ui.trace_status_category',  fallback: 'Skipped · category cap', cls: 'trace-status--skip' },
        skipped_theme_quota:      { key: 'ui.trace_status_themeq',    fallback: 'Skipped · theme quota', cls: 'trace-status--skip' },
        skipped_region_quota:     { key: 'ui.trace_status_regionq',   fallback: 'Skipped · region quota', cls: 'trace-status--skip' },
        not_reached:              { key: 'ui.trace_status_not_reached',  fallback: 'Not reached',        cls: 'trace-status--muted' },
    };

    function pct(frac) {
        return frac == null ? '—' : `${(Number(frac) * 100).toFixed(1)}%`;
    }

    function fmtBoosts(boosts) {
        const entries = Object.entries(boosts || {});
        if (!entries.length) return '—';
        return entries.map(([k, v]) => `${k} +${v}`).join(', ');
    }

    // Preference-satisfaction display — Summary tab shows the full sentence,
    // Preferences tab shows the short "x/y". Both read the single source of
    // truth computed by the engine (portfolio_metrics.preference_satisfaction).
    function renderPreferenceSatisfaction(portfolio) {
        const ps = portfolio.portfolio_metrics?.preference_satisfaction;
        const summaryEl = document.getElementById('pref-satisfaction-summary');
        const shortEl = document.getElementById('pref-satisfaction-short');
        if (!ps) {
            if (summaryEl) summaryEl.textContent = '—';
            if (shortEl) shortEl.textContent = '';
            return;
        }
        if (summaryEl) {
            summaryEl.textContent = t(
                'ui.pref_summary',
                '{fulfilled} of {total} preferences fulfilled.'
            ).replace('{fulfilled}', ps.fulfilled).replace('{total}', ps.total);
        }
        if (shortEl) {
            shortEl.textContent = t('ui.pref_summary_short', 'Preferences fulfilled: {x}')
                .replace('{x}', ps.display);
        }
    }

    // Per-fund toggle chips for the Performance tab — each chip controls the
    // visibility of one fund's NAV line in the performance chart.
    function renderFundToggles(fundSeries) {
        const chartFrame = document.querySelector('#tab-perf .chart-frame');
        if (!chartFrame || !fundSeries.length) return;

        // Remove any existing toggle row before re-rendering.
        const existing = chartFrame.querySelector('.fund-toggles');
        if (existing) existing.remove();

        const row = document.createElement('div');
        row.className = 'fund-toggles stress-overlay-toggles';
        row.setAttribute('aria-label', t('ui.fund_toggle_label', 'Toggle individual fund lines'));

        const palette = ['#5B6770', '#7D5260', '#2E7D32', '#E65100', '#0277BD', '#6D4C41'];

        fundSeries.forEach((fund, i) => {
            const color = palette[i % palette.length];
            const chip = document.createElement('button');
            chip.className = 'stress-toggle active';
            chip.type = 'button';
            chip.dataset.isin = fund.isin;
            chip.innerHTML = `<span class="stress-toggle__dot" style="background:${color}"></span><span>${fund.name || fund.isin}</span>`;

            chip.addEventListener('click', () => {
                const canvas = document.getElementById('chart-performance');
                const chart = window.Chart.getChart(canvas);
                if (!chart) return;
                // Dataset index 0 = portfolio; funds start at 1.
                const dsIndex = chart.data.datasets.findIndex(
                    (ds, idx) => idx > 0 && ds._fundIsin === fund.isin
                );
                if (dsIndex >= 0) {
                    chart.setDatasetVisibility(dsIndex, !chart.isDatasetVisible(dsIndex));
                    chip.classList.toggle('active');
                    chart.update();
                }
            });

            row.appendChild(chip);
        });

        chartFrame.insertBefore(row, chartFrame.firstChild);
    }

    function renderDecisionTrace(trace, showTraces) {
        const host = decisionTraceDetail;
        if (!host) return;
        host.innerHTML = '';
        const hasTrace = !!(trace && (trace.ranking || trace.selection || trace.allocation));
        host.classList.toggle('hidden', !showTraces || !hasTrace);
        if (!showTraces || !hasTrace) return;

        const heading = (text) => {
            const h = document.createElement('h3');
            h.className = 'decision-trace__heading';
            h.textContent = text;
            host.appendChild(h);
        };
        const note = (text) => {
            const p = document.createElement('p');
            p.className = 'decision-trace__note';
            p.textContent = text;
            host.appendChild(p);
        };

        // Ranking & selection
        const ranking = trace.ranking;
        if (ranking?.candidates?.length) {
            heading(t('ui.trace_ranking_title', 'Ranking & selection'));
            const f = ranking.formula || {};
            note(t('ui.trace_formula',
                'Base score = Sharpe×{s} + max-drawdown×{m} + TER×{t} (each normalised 0–10); preference boosts are added on top.')
                .replace('{s}', f.sharpe).replace('{m}', f.mdd).replace('{t}', f.ter));
            host.appendChild(buildRankingTable(ranking.candidates, trace.selection?.events || []));
        }

        // Selection decisions (two-pass, coverage-first): every pick and skip
        // is listed in the order the engine made it — pass 1 (coverage of
        // preferred regions/themes) first, then pass 2 (best-score fill).
        const events = trace.selection?.events || [];
        if (events.length) {
            heading(t('ui.trace_events_title', 'Selection decisions'));
            note(t('ui.trace_pass_note',
                'Pass 1 covers your preferred regions and themes with the best matching funds; pass 2 fills the remaining slots with the best funds by score.'));
            host.appendChild(buildEventList(events));
        }

        // Allocation
        const alloc = trace.allocation;
        if (alloc?.funds?.length) {
            heading(t('ui.trace_alloc_title', 'Allocation'));
            if (alloc.satellite_cap_applied) {
                note(t('ui.trace_sat_cap', 'Satellite total was capped at 30%.'));
            }
            host.appendChild(buildAllocationTable(alloc.funds));
        }
    }

    function buildRankingTable(candidates, events) {
        // Pass-1 coverage info per ISIN: which preference dimensions the fund
        // was picked for, and whether this trace contains pass-1 picks at all.
        const pass1Dims = {};
        let hasPass1 = false;
        (events || []).forEach(e => {
            if (e.type === 'pass1_select') {
                hasPass1 = true;
                if (e.isin) pass1Dims[e.isin] = e.matched || [];
            }
        });

        const table = document.createElement('table');
        table.className = 'trace-table';
        table.innerHTML = `
            <thead><tr>
                <th>#</th>
                <th>${t('ui.col_fund', 'Fund')}</th>
                <th>${t('ui.trace_col_base', 'Base')}</th>
                <th>${t('ui.trace_col_boosts', 'Boosts')}</th>
                <th>${t('ui.trace_col_final', 'Final')}</th>
                <th>${t('ui.trace_col_status', 'Status')}</th>
            </tr></thead>`;
        const tbody = document.createElement('tbody');
        candidates.forEach(c => {
            const st = TRACE_STATUS[c.status] || TRACE_STATUS.not_reached;
            let statusLabel;
            if (c.status === 'selected_pass1_coverage') {
                const dims = (pass1Dims[c.isin] || [])
                    .map(d => d.dimension === 'theme' ? t('ui.dim_theme', 'theme') : t('ui.dim_region', 'region'))
                    .join(' + ');
                statusLabel = t('ui.trace_status_pass1', 'Selected (1) · {dims} match')
                    .replace('{dims}', dims || t('ui.dim_pref', 'preference'));
            } else if (c.status === 'selected' && hasPass1) {
                statusLabel = t('ui.trace_status_selected2', 'Selected (2)');
            } else {
                statusLabel = t(st.key, st.fallback);
            }
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${c.rank}</td>
                <td>
                    <div class="trace-fund-name">${escHtml(c.name || c.isin || '')}</div>
                    <div class="trace-fund-sub">${escHtml(c.provider || '')}</div>
                </td>
                <td>${c.base ?? '—'}</td>
                <td>${escHtml(fmtBoosts(c.boosts))}</td>
                <td><strong>${c.final ?? '—'}</strong></td>
                <td><span class="trace-status ${st.cls}">${statusLabel}</span></td>`;
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        return table;
    }

    // Pretty-print a list of {dimension, value} preference matches, e.g.
    // "region germany, theme sustainability".
    function fmtDims(dims) {
        return (dims || [])
            .map(d => `${d.dimension === 'theme' ? t('ui.dim_theme', 'theme') : t('ui.dim_region', 'region')} ${String(d.value || '').toLowerCase()}`)
            .join(', ');
    }

    function buildEventList(events) {
        const ul = document.createElement('ul');
        ul.className = 'decision-trace__events';
        events.forEach(e => {
            let text;
            switch (e.type) {
                case 'pass1_select': {
                    const matched = fmtDims(e.matched);
                    const also = fmtDims(e.also_satisfies);
                    text = t('ui.trace_ev_pass1', 'Pass 1 · Coverage pick: {name} — matches {matched}.')
                        .replace('{name}', e.name || e.isin)
                        .replace('{matched}', matched);
                    if (also) {
                        text += ' ' + t('ui.trace_ev_also', 'Also covers: {also}.').replace('{also}', also);
                    }
                    if (Array.isArray(e.quota_breached) && e.quota_breached.length) {
                        text += ' ' + t('ui.trace_ev_breach', '(quota exceeded: {q})')
                            .replace('{q}', e.quota_breached.join(', '));
                    }
                    break;
                }
                case 'pass2_select':
                    text = t('ui.trace_ev_pass2', 'Pass 2 · Fill pick: {name} — next best score.')
                        .replace('{name}', e.name || e.isin);
                    break;
                case 'selection_skip': {
                    const reasonKeys = {
                        provider_cap: 'ui.trace_skip_provider',
                        category_cap: 'ui.trace_skip_category',
                        theme_quota: 'ui.trace_skip_themeq',
                        region_quota: 'ui.trace_skip_regionq',
                    };
                    const reason = reasonKeys[e.reason]
                        ? t(reasonKeys[e.reason], e.reason)
                        : (e.reason || '');
                    text = t('ui.trace_ev_skip', 'Skipped {name}: {reason}.')
                        .replace('{name}', e.name || e.isin)
                        .replace('{reason}', reason);
                    if (Array.isArray(e.dimensions) && e.dimensions.length) {
                        text = text.replace(/\.$/, '') + ` (${e.dimensions.join(', ')}).`;
                    }
                    break;
                }
                case 'coverage_unfulfillable':
                    text = t('ui.trace_ev_unfulfillable', 'Preference not covered: {dim} "{value}" — {reason}.')
                        .replace('{dim}', e.dimension || '')
                        .replace('{value}', e.value || '')
                        .replace('{reason}', e.reason || '');
                    break;
                case 'caps_relaxed':
                    text = t('ui.trace_ev_relaxed', 'Diversification caps relaxed to reach the target fund count.');
                    break;
                case 'etf_fallback_fill':
                    text = t('ui.trace_ev_etffill', 'ETF-only fallback: added active fund {name}.').replace('{name}', e.name || e.isin);
                    break;
                default:
                    text = e.type;
            }
            const li = document.createElement('li');
            li.textContent = text;
            ul.appendChild(li);
        });
        return ul;
    }

    function buildAllocationTable(funds) {
        const table = document.createElement('table');
        table.className = 'trace-table';
        table.innerHTML = `
            <thead><tr>
                <th>${t('ui.col_fund', 'Fund')}</th>
                <th>${t('ui.trace_col_class', 'Class')}</th>
                <th>${t('ui.trace_col_invvol', 'Inv-vol')}</th>
                <th>${t('ui.trace_col_clip', 'After clip')}</th>
                <th>${t('ui.trace_col_tilt', 'Tilt')}</th>
                <th>${t('ui.trace_col_weight', 'Weight')}</th>
            </tr></thead>`;
        const tbody = document.createElement('tbody');
        funds.forEach(f => {
            const cls = f.class === 'satellite'
                ? t('ui.class_satellite', 'Satellite')
                : t('ui.class_core', 'Core');
            const bounds = Array.isArray(f.tier_bounds)
                ? ` (${pct(f.tier_bounds[0])}–${pct(f.tier_bounds[1])})` : '';
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><div class="trace-fund-name">${escHtml(f.name || f.isin || '')}</div></td>
                <td>${escHtml(cls)}</td>
                <td>${pct(f.inv_vol_raw)}</td>
                <td>${pct(f.after_clip)}<span class="trace-fund-sub">${bounds}</span></td>
                <td>${f.regional_tilt ? '×1.2' : '—'}</td>
                <td><strong>${pct(f.final_weight)}</strong></td>`;
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        return table;
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
});
