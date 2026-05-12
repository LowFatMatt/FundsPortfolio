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
    const langSelect      = document.getElementById('lang-select');
    const fundTableBody   = document.getElementById('fund-table-body');
    const fundCount       = document.getElementById('fund-count');
    const weightedFeeVal  = document.getElementById('weighted-fee-val');
    const assetClassSummary = document.getElementById('asset-class-summary');
    const regionSummary   = document.getElementById('region-summary');

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------
    let currentPortfolioId = null;
    const supportedLangs   = ['en', 'de'];
    let currentLang        = 'en';
    let uiStrings          = {};

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
    restartBtn.addEventListener('click', resetApp);
    startFreshBtn.addEventListener('click', () => {
        currentPortfolioId = null;
        qForm.reset();
        clearResults();
        showFormView(null);
    });
    resumeForm.addEventListener('submit', handleResume);

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
            renderForm(data.sections || []);
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

        sections.forEach(section => {
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

            const hint = section.display_hint || null;

            if (hint === 'cards' && section.type === 'single_select') {
                group.appendChild(renderCardGroup(section));
            } else if (hint === 'chips') {
                group.appendChild(renderChipGroup(section));
            } else if (section.type === 'single_select') {
                group.appendChild(renderSelectField(section));
            } else if (section.type === 'multi_select') {
                group.appendChild(renderCheckboxList(section));
            } else {
                const input = document.createElement('input');
                input.type = 'text';
                input.id   = section.id;
                input.name = section.id;
                if (section.required) input.required = true;
                group.appendChild(input);
            }

            qFields.appendChild(group);
        });
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

    // Chip grid (display_hint: "chips")
    function renderChipGroup(section) {
        const wrap = document.createElement('div');
        wrap.className = 'chip-grid';

        const isMulti = section.type === 'multi_select';

        section.options.forEach(opt => {
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

            chip.addEventListener('click', () => {
                if (isMulti) {
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

            // Loss tolerance
            'loss_tolerance_low_tolerance':  `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="14" y="20" width="28" height="20" rx="3"/><path d="M20 20v-4a8 8 0 0116 0v4"/><circle cx="28" cy="30" r="2" fill="currentColor"/></svg>`,
            'loss_tolerance_high_tolerance': `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18,28 24,34 38,22"/><rect x="12" y="16" width="32" height="26" rx="4"/></svg>`,

            // ESG
            'no_esg_requirement':  `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="28" cy="28" r="16"/><line x1="16" y1="16" x2="40" y2="40"/></svg>`,
            'esg_basic':           `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M28 14c-6 8-10 14-10 20a10 10 0 0020 0c0-6-4-12-10-20z"/></svg>`,
            'esg_enhanced':        `<svg viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M28 12c-8 10-14 18-14 22a14 14 0 0028 0c0-4-6-12-14-22z"/><line x1="28" y1="42" x2="28" y2="30"/></svg>`,

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

        const formData    = new FormData(qForm);
        const userAnswers = {};

        for (const [key, value] of formData.entries()) {
            if (userAnswers[key]) {
                if (!Array.isArray(userAnswers[key])) userAnswers[key] = [userAnswers[key]];
                userAnswers[key].push(value);
            } else {
                const checkboxes = qForm.querySelectorAll(`input[type="checkbox"][name="${key}"]`);
                userAnswers[key] = checkboxes.length > 0 ? [value] : value;
            }
        }

        // Also gather card-grid radios (they are standard radio inputs, FormData picks them up)
        // and chip hidden inputs — already picked up by FormData

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

            displayResults(data);
        } catch (err) {
            showError(err.message);
            setLoadingState(false);
        }
    }

    // -------------------------------------------------------------------------
    // Display results
    // -------------------------------------------------------------------------
    function displayResults(portfolio) {
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
            const fee = portfolio.weighted_fee;
            weightedFeeVal.textContent = fee != null ? `${Number(fee).toFixed(3)}%` : '—';
        }

        // Decision summary (Preferences tab)
        if (decisionSummaryText) {
            decisionSummaryText.textContent =
                portfolio.explanations?.summary || t('ui.summary_unavailable');
        }

        if (decisionFilters) {
            decisionFilters.innerHTML = '';
            (portfolio.decision_trace?.filters || []).forEach(f => {
                decisionFilters.appendChild(makeFilterPill(`${f.name}: ${f.before}→${f.after}`));
            });
            (portfolio.decision_trace?.relaxations || []).forEach(r => {
                const label = r.reason ? `${r.name}: ${r.reason}` : `relaxation: ${r.name} ${r.before}→${r.after}`;
                decisionFilters.appendChild(makeFilterPill(label));
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

        if (assetClassSummary) {
            assetClassSummary.textContent = acEntries.length
                ? acEntries.map(([k, v]) => `${acLabel(k)} ${(v * 100).toFixed(0)}%`).join(' · ')
                : '—';
        }
        if (regionSummary) {
            regionSummary.textContent = rEntries.length
                ? rEntries.map(([k, v]) => `${rLabel(k)} ${(v * 100).toFixed(0)}%`).join(' · ')
                : '—';
        }
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

        window.FundsCharts.renderPerformanceChart('chart-performance', {
            portfolio: perf.portfolio_series || [],
            benchmark: perf.benchmark
                ? { series: perf.benchmark_series || [], label: perf.benchmark.name || t('ui.benchmark', 'Benchmark') }
                : null,
            stressBands,
            labels: { portfolio: t('ui.portfolio', 'Portfolio'), benchmark: t('ui.benchmark', 'Benchmark') },
        });

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
                <td><span class="fund-alloc">${(rec.allocation_percent || 0).toFixed(1)}%</span></td>
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
            });

            fundTableBody.appendChild(tr);
            fundTableBody.appendChild(detailTr);
        });
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
        if (assetClassSummary)    assetClassSummary.textContent = '—';
        if (regionSummary)        regionSummary.textContent    = '—';
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
            Object.entries(prefillAnswers).forEach(([key, value]) => {
                const elements = qForm.querySelectorAll(`[name="${key}"]`);
                if (!elements.length) return;

                if (elements[0].type === 'checkbox') {
                    const arr = Array.isArray(value) ? value : [value];
                    elements.forEach(cb => { cb.checked = arr.includes(cb.value); });

                    // Also update chip visual state
                    elements.forEach(cb => {
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

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
});
