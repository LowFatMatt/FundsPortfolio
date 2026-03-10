document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const qForm = document.getElementById('questionnaire-form');
    const qFields = document.getElementById('questionnaire-fields');
    const loadingView = document.getElementById('loading-view');
    const formView = document.getElementById('form-view');
    const resultsView = document.getElementById('results-view');
    const errorView = document.getElementById('error-view');
    const errorMessage = document.getElementById('error-message');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnSpinner = document.getElementById('btn-spinner');
    const restartBtn = document.getElementById('restart-btn');

    // Results Elements
    const scoreVal = document.getElementById('score-val');
    const recList = document.getElementById('recommendations-list');

    // Initialize Application
    loadQuestionnaire();

    // Event Listeners
    qForm.addEventListener('submit', handleSubmission);
    restartBtn.addEventListener('click', resetApp);

    // Core Functions
    async function loadQuestionnaire() {
        try {
            const response = await fetch('/api/questionnaire');
            if (!response.ok) throw new Error('Failed to load questionnaire schema');
            
            const data = await response.json();
            renderForm(data.sections || []);
            
            loadingView.classList.add('hidden');
            formView.classList.remove('hidden');
        } catch (err) {
            showError("Could not connect to server to load the questionnaire.");
            console.error(err);
        }
    }

    function renderForm(sections) {
        qFields.innerHTML = '';
        
        sections.forEach((section) => {
            const group = document.createElement('div');
            group.className = 'form-group';
            
            const label = document.createElement('label');
            label.htmlFor = section.id;
            label.textContent = section.title || section.id.replace('_', ' ').toUpperCase();
            
            if (section.required) {
                const reqSpan = document.createElement('span');
                reqSpan.textContent = ' *';
                reqSpan.style.color = 'var(--accent)';
                label.appendChild(reqSpan);
            }
            
            group.appendChild(label);
            
            if (section.description) {
                const desc = document.createElement('p');
                desc.style.fontSize = '0.85rem';
                desc.style.color = 'var(--text-secondary)';
                desc.style.marginBottom = '0.5rem';
                desc.textContent = section.description;
                group.appendChild(desc);
            }
            
            if (section.type === 'single_select') {
                const wrapper = document.createElement('div');
                wrapper.className = 'select-wrapper';
                
                const select = document.createElement('select');
                select.id = section.id;
                select.name = section.id;
                if (section.required) select.required = true;
                
                const defaultOpt = document.createElement('option');
                defaultOpt.value = '';
                defaultOpt.textContent = 'Select an option...';
                defaultOpt.disabled = true;
                defaultOpt.selected = true;
                select.appendChild(defaultOpt);
                
                (section.options || []).forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt.value;
                    option.textContent = opt.label;
                    select.appendChild(option);
                });
                
                wrapper.appendChild(select);
                group.appendChild(wrapper);
            } else {
                // Fallback for unexpected types
                const input = document.createElement('input');
                input.type = 'text';
                input.id = section.id;
                input.name = section.id;
                if (section.required) input.required = true;
                group.appendChild(input);
            }

            qFields.appendChild(group);
        });
    }

    async function handleSubmission(e) {
        e.preventDefault();
        
        // Hide errors, show spinner
        errorView.classList.add('hidden');
        setLoadingState(true);

        const formData = new FormData(qForm);
        const userAnswers = Object.fromEntries(formData.entries());

        try {
            const response = await fetch('/api/portfolio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_answers: userAnswers })
            });

            const data = await response.json();

            if (!response.ok) {
                const details = data.details && data.details.length ? `\nReason: ${data.details.join('; ')}` : '';
                throw new Error((data.error || 'Failed to generate portfolio') + details);
            }

            displayResults(data);

        } catch (err) {
            showError(err.message);
            setLoadingState(false);
        }
    }

    function displayResults(portfolio) {
        setLoadingState(false);
        formView.classList.add('hidden');
        resultsView.classList.remove('hidden');

        // Extract risk score directly from payload or default
        const approach = portfolio.user_answers?.risk_approach || 'Unknown';
        scoreVal.textContent = approach.replace('_', ' ').toUpperCase();

        recList.innerHTML = '';
        
        if (!portfolio.recommendations || !portfolio.recommendations.length) {
            recList.innerHTML = '<p style="color:var(--text-secondary)">No valid recommendations available.</p>';
            return;
        }

        portfolio.recommendations.forEach(rec => {
            const item = document.createElement('div');
            item.className = 'fund-item form-group'; // Reuse animation class

            const isinLabel = rec.isin ? `<span class="badge ${rec.asset_class?.toLowerCase() || 'bond'}">${rec.asset_class || 'BOND'}</span>` : '';
            
            item.innerHTML = `
                <div class="fund-meta">
                    <h4>${rec.name || 'Unknown Fund'} ${isinLabel}</h4>
                    <p>${rec.isin || 'N/A'} • Exp. Ratio: ${(rec.yearly_fee || 0).toFixed(2)}%</p>
                    <p style="font-size: 0.8rem; margin-top: 0.5rem">${rec.rationale || ''}</p>
                </div>
                <div class="fund-allocation">
                    <div class="allocation-percent">${(rec.allocation_percent || 0).toFixed(1)}%</div>
                    <div class="allocation-label">Target Weight</div>
                </div>
            `;
            
            recList.appendChild(item);
        });
    }

    function resetApp() {
        resultsView.classList.add('hidden');
        errorView.classList.add('hidden');
        qForm.reset();
        formView.classList.remove('hidden');
        
        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // UI Helpers
    function setLoadingState(isLoading) {
        submitBtn.disabled = isLoading;
        if (isLoading) {
            btnText.textContent = 'Analyzing...';
            btnSpinner.classList.remove('hidden');
        } else {
            btnText.textContent = 'Generate Portfolio';
            btnSpinner.classList.add('hidden');
        }
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorView.classList.remove('hidden');
    }
});
