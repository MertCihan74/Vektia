/**
 * Vektia Charts Module
 * Chart.js ile dashboard grafikleri.
 * Chart.js CDN'den yüklenir.
 */

let _detectionChartInstance = null;
let _riskChartInstance = null;

/**
 * Tespit Zaman Serisi Grafiği
 */
function createDetectionChart(canvasId, data = null) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    if (_detectionChartInstance) {
        _detectionChartInstance.destroy();
    }

    // Gelen veriyi kullan veya boş grafik çiz
    const hours = data ? data.labels : [];
    const cleanData = data ? data.clean : [];
    const suspiciousData = data ? data.suspicious : [];
    const flaggedData = data ? data.flagged : [];

    _detectionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: typeof i18n !== 'undefined' ? i18n.t('chart_clean') : 'Temiz',
                    data: cleanData,
                    borderColor: '#00e68a',
                    backgroundColor: 'rgba(0, 230, 138, 0.05)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                },
                {
                    label: typeof i18n !== 'undefined' ? i18n.t('chart_suspicious') : 'Şüpheli',
                    data: suspiciousData,
                    borderColor: '#ff8c42',
                    backgroundColor: 'rgba(255, 140, 66, 0.05)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                },
                {
                    label: typeof i18n !== 'undefined' ? i18n.t('chart_flagged') : 'İşaretli',
                    data: flaggedData,
                    borderColor: '#ff2e63',
                    backgroundColor: 'rgba(255, 46, 99, 0.05)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#8888a8',
                        font: { family: 'Inter', size: 11 },
                        boxWidth: 12,
                        boxHeight: 3,
                        borderRadius: 2,
                        padding: 16,
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(12, 12, 24, 0.95)',
                    titleColor: '#e8e8f0',
                    bodyColor: '#8888a8',
                    borderColor: 'rgba(255, 255, 255, 0.06)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 12,
                    titleFont: { family: 'Inter', weight: '600' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                    ticks: { color: '#555570', font: { size: 10 }, maxTicksLimit: 12 },
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                    ticks: { color: '#555570', font: { size: 10 } },
                    beginAtZero: true,
                },
            },
        },
    });
}

/**
 * Risk Dağılım Doughnut Grafiği
 */
function createRiskDistributionChart(canvasId, data = null) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    if (_riskChartInstance) {
        _riskChartInstance.destroy();
    }

    const chartData = data || {
        clean: 0,
        low: 0,
        suspicious: 0,
        high: 0,
        confirmed: 0,
    };

    _riskChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: typeof i18n !== 'undefined' ? [i18n.t('chart_clean'), i18n.t('chart_low'), i18n.t('chart_suspicious'), i18n.t('chart_high'), i18n.t('chart_confirmed')] : ['Temiz', 'Düşük Risk', 'Şüpheli', 'Yüksek Risk', 'Kesin Bot'],
            datasets: [{
                data: Object.values(chartData),
                backgroundColor: [
                    'rgba(0, 230, 138, 0.8)',
                    'rgba(255, 217, 61, 0.8)',
                    'rgba(255, 140, 66, 0.8)',
                    'rgba(255, 46, 99, 0.8)',
                    'rgba(255, 46, 99, 1)',
                ],
                borderColor: '#0c0c18',
                borderWidth: 2,
                hoverBorderWidth: 0,
                hoverOffset: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#8888a8',
                        font: { family: 'Inter', size: 11 },
                        padding: 12,
                        boxWidth: 10,
                        boxHeight: 10,
                        borderRadius: 3,
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(12, 12, 24, 0.95)',
                    titleColor: '#e8e8f0',
                    bodyColor: '#8888a8',
                    borderColor: 'rgba(255, 255, 255, 0.06)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    callbacks: {
                        label: (ctx) => ` ${ctx.label}: %${ctx.parsed.toFixed(1)}`,
                    },
                },
            },
        },
    });
}
