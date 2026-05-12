/* eslint-env browser */
/**
 * Lazy chart loader and renderers for the Performance, Volatility and
 * breakdown panels. Loads Chart.js v4 + plugins from CDN on first use.
 *
 * Public surface (FundsCharts):
 *   await FundsCharts.ensureChartJs()
 *   FundsCharts.renderBreakdownDonut(canvasId, { labels, values, palette, legendId, formatLabel })
 *   FundsCharts.renderPerformanceChart(canvasId, { portfolio, benchmark, stressBands, locale, labels })
 *   FundsCharts.renderVolatilityChart(canvasId, { rows, locale, labels })
 *
 * Renderers destroy any existing chart on the same canvas before drawing.
 */
(function (window) {
    'use strict';

    const CDN = {
        chartjs:    'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js',
        adapter:    'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js',
        annotation: 'https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.1.0/dist/chartjs-plugin-annotation.min.js',
    };

    let _loadingPromise = null;
    const _charts = new Map(); // canvasId -> Chart instance

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[data-src="${src}"]`);
            if (existing) { existing.addEventListener('load', resolve); existing.addEventListener('error', reject); return; }
            const s = document.createElement('script');
            s.src = src;
            s.async = true;
            s.dataset.src = src;
            s.onload  = () => resolve();
            s.onerror = () => reject(new Error('Failed to load ' + src));
            document.head.appendChild(s);
        });
    }

    async function ensureChartJs() {
        if (window.Chart && window.Chart.registry) return window.Chart;
        if (_loadingPromise) return _loadingPromise;
        _loadingPromise = (async () => {
            await loadScript(CDN.chartjs);
            await loadScript(CDN.adapter);
            await loadScript(CDN.annotation);
            if (window['chartjs-plugin-annotation']) {
                window.Chart.register(window['chartjs-plugin-annotation']);
            } else if (window.Annotation) {
                window.Chart.register(window.Annotation);
            }
            return window.Chart;
        })();
        return _loadingPromise;
    }

    function destroyExisting(canvasId) {
        const prev = _charts.get(canvasId);
        if (prev) { try { prev.destroy(); } catch (e) { /* ignore */ } _charts.delete(canvasId); }
    }

    const DEFAULT_PALETTE = ['#6750A4', '#7D5260', '#386A20', '#7E5700', '#1F4E79', '#B3261E', '#5E5E5E', '#0288D1'];

    function fmtPct(value, decimals = 1) {
        if (value === null || value === undefined || Number.isNaN(value)) return null;
        return `${(value * 100).toFixed(decimals)}%`;
    }

    function renderBreakdownDonut(canvasId, opts) {
        const { labels = [], values = [], palette = DEFAULT_PALETTE, legendId = null, formatLabel = (k) => k } = opts || {};
        if (!window.Chart) return;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyExisting(canvasId);

        if (!labels.length) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (legendId) {
                const legend = document.getElementById(legendId);
                if (legend) legend.innerHTML = '';
            }
            return;
        }

        const colors = labels.map((_, i) => palette[i % palette.length]);
        const chart = new window.Chart(canvas, {
            type: 'doughnut',
            data: { labels: labels.map(formatLabel), datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '62%',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: { label: (item) => `${item.label}: ${fmtPct(item.raw, 1)}` },
                    },
                },
            },
        });
        _charts.set(canvasId, chart);

        if (legendId) {
            const legend = document.getElementById(legendId);
            if (legend) {
                legend.innerHTML = labels.map((k, i) =>
                    `<span class="legend-item"><span class="legend-swatch" style="background:${colors[i]}"></span>${formatLabel(k)} ${fmtPct(values[i], 0)}</span>`
                ).join('');
            }
        }
    }

    function buildAnnotations(stressBands) {
        const annotations = {};
        (stressBands || []).filter(b => b.enabled).forEach((b, i) => {
            annotations[`stress_${b.id || i}`] = {
                type: 'box',
                xMin: b.start,
                xMax: b.end,
                backgroundColor: hexToRgba(b.color || '#E53935', 0.13),
                borderColor: hexToRgba(b.color || '#E53935', 0.45),
                borderWidth: 1,
                label: { content: b.label || b.id || '', display: false },
            };
        });
        return annotations;
    }

    function hexToRgba(hex, alpha) {
        const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
        if (!m) return `rgba(229,57,53,${alpha})`;
        const r = parseInt(m[1].slice(0, 2), 16);
        const g = parseInt(m[1].slice(2, 4), 16);
        const b = parseInt(m[1].slice(4, 6), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    }

    function renderPerformanceChart(canvasId, opts) {
        const { portfolio = [], benchmark = null, stressBands = [], labels = {} } = opts || {};
        if (!window.Chart) return;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyExisting(canvasId);

        const datasets = [{
            label: labels.portfolio || 'Portfolio',
            data: portfolio.map(p => ({ x: p.d, y: p.v })),
            borderColor: '#6750A4',
            backgroundColor: 'rgba(103,80,164,0.10)',
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 0,
            fill: false,
        }];

        if (benchmark && benchmark.series && benchmark.series.length) {
            datasets.push({
                label: benchmark.label || labels.benchmark || 'Benchmark',
                data: benchmark.series.map(p => ({ x: p.d, y: p.v })),
                borderColor: '#7D5260',
                borderWidth: 1.5,
                borderDash: [6, 4],
                tension: 0.25,
                pointRadius: 0,
                fill: false,
            });
        }

        const chart = new window.Chart(canvas, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { type: 'time', time: { unit: 'year' }, grid: { display: false } },
                    y: { grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { callback: v => v.toFixed(0) } },
                },
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
                    annotation: { annotations: buildAnnotations(stressBands) },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`,
                        },
                    },
                },
            },
        });
        _charts.set(canvasId, chart);
    }

    function renderVolatilityChart(canvasId, opts) {
        const { rows = [], labels = {} } = opts || {};
        if (!window.Chart) return;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyExisting(canvasId);

        const xLabels = rows.map(r => r.name || r.isin || '');
        const ds = (key, color, dsLabel) => ({
            label: dsLabel,
            data: rows.map(r => (r[key] != null ? r[key] * 100 : null)),
            backgroundColor: color,
            borderWidth: 0,
            borderRadius: 4,
        });

        const chart = new window.Chart(canvas, {
            type: 'bar',
            data: {
                labels: xLabels,
                datasets: [
                    ds('vol_1y', '#6750A4', labels.vol_1y || 'Vol 1Y'),
                    ds('vol_3y', '#7D5260', labels.vol_3y || 'Vol 3Y'),
                    ds('vol_5y', '#386A20', labels.vol_5y || 'Vol 5Y'),
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11 }, autoSkip: false, maxRotation: 35, minRotation: 20 } },
                    y: { grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { callback: v => `${v.toFixed(1)}%` } },
                },
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y == null ? 'n/a' : ctx.parsed.y.toFixed(2) + '%'}` } },
                },
            },
        });
        _charts.set(canvasId, chart);
    }

    window.FundsCharts = {
        ensureChartJs,
        renderBreakdownDonut,
        renderPerformanceChart,
        renderVolatilityChart,
    };

})(window);
