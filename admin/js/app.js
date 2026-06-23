/**
 * Vektia Admin Dashboard — Main Application
 * Sayfa yönlendirme, tema ve genel uygulama mantığı.
 */

/**
 * Utility: Zaman formatı (relative)
 */
function timeAgo(dateStr) {
    if (!dateStr) return '—';
    const now = new Date();
    const date = new Date(dateStr);
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return `${seconds}sn önce`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}dk önce`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}sa önce`;
    return `${Math.floor(seconds / 86400)}gün önce`;
}

/**
 * Utility: Risk skoru rengi
 */
function getRiskColor(score) {
    if (score >= 0.8) return 'high';
    if (score >= 0.5) return 'medium';
    return 'low';
}

/**
 * Utility: Badge HTML
 */
function statusBadge(status) {
    const labels = {
        active: 'Aktif', flagged: 'İşaretli', banned: 'Banlı',
        whitelisted: 'Beyaz Liste', clean: 'Temiz', low: 'Düşük',
        suspicious: 'Şüpheli', high: 'Yüksek', confirmed: 'Kesin Bot',
    };
    return `<span class="badge badge-${status}">${labels[status] || status}</span>`;
}

/**
 * Risk score bar HTML
 */
function riskScoreBar(score) {
    const pct = Math.round(score * 100);
    const color = getRiskColor(score);
    return `
        <div class="risk-bar-container">
            <div class="risk-bar">
                <div class="risk-bar-fill ${color}" style="width: ${pct}%"></div>
            </div>
            <span class="risk-score-value" style="color: var(--accent-${color === 'high' ? 'red' : color === 'medium' ? 'orange' : 'green'})">${pct}%</span>
        </div>
    `;
}

/**
 * Dashboard yükle
 */
async function loadDashboard() {
    try {
        const data = await VektiaAPI.getDashboard();

        // Stat kartlarını güncelle
        setStatValue('totalPlayers', data.total_players || 0);
        setStatValue('activePlayers', data.active_players || 0);
        setStatValue('flaggedPlayers', data.flagged_players || 0);
        setStatValue('bannedPlayers', data.banned_players || 0);

        // Pipeline stats
        if (data.pipeline) {
            setStatValue('totalEvents', formatNumber(data.pipeline.total_events || 0));
        }

        // Grafikleri Güncelle
        if (data.chart_data) {
            createDetectionChart('detectionChart', data.chart_data.timeline);
            createRiskDistributionChart('riskChart', data.chart_data.risk_distribution);
        }
    } catch (err) {
        console.error('Dashboard yükleme hatası:', err);
    }
}

/**
 * Uyarıları yükle
 */
async function loadAlerts() {
    try {
        const data = await VektiaAPI.getAlerts(20);
        const container = document.getElementById('alertFeed');
        if (!container) return;

        if (!data.alerts || data.alerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🛡️</div>
                    <div class="empty-text">Henüz uyarı yok — sistem temiz!</div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.alerts.map(alert => `
            <div class="alert-item">
                <div class="alert-dot ${alert.risk_level || 'suspicious'}"></div>
                <div class="alert-content">
                    <div class="alert-title">${alert.player_id} — ${statusBadge(alert.risk_level)}</div>
                    <div class="alert-meta">
                        Katman ${alert.layer} | Risk: ${(alert.risk_score * 100).toFixed(0)}% | ${timeAgo(alert.created_at)}
                    </div>
                </div>
                <div class="alert-actions">
                    <button class="btn btn-danger btn-sm" onclick="banPlayer('${alert.player_id}')">🚫 Ban</button>
                    <button class="btn btn-ghost btn-sm" onclick="whitelistPlayer('${alert.player_id}')">✅ Temiz</button>
                </div>
            </div>
        `).join('');

        // Nav badge güncelle
        updateAlertBadge(data.alerts.length);
    } catch (err) {
        console.error('Uyarı yükleme hatası:', err);
    }
}

/**
 * Oyuncu listesini yükle
 */
async function loadPlayers(status = null) {
    try {
        const params = { limit: 50, sort_by: 'risk_score' };
        if (status) params.status = status;

        const data = await VektiaAPI.getPlayers(params);
        const tbody = document.getElementById('playersTableBody');
        if (!tbody) return;

        if (!data.players || data.players.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="6" class="empty-state">
                    <div class="empty-icon">👤</div>
                    <div class="empty-text">Henüz oyuncu kaydı yok</div>
                </td></tr>
            `;
            return;
        }

        tbody.innerHTML = data.players.map(p => `
            <tr>
                <td><span class="player-id">${p.player_id}</span></td>
                <td>${statusBadge(p.status)}</td>
                <td>${statusBadge(p.risk_level)}</td>
                <td>${riskScoreBar(p.risk_score)}</td>
                <td style="font-family: var(--font-mono); font-size: 0.82rem;">${formatNumber(p.total_events)}</td>
                <td style="color: var(--text-muted); font-size: 0.8rem;">${timeAgo(p.last_seen)}</td>
                <td>
                    <button class="btn btn-ghost btn-sm" onclick="openPlayerModal('${p.player_id}')">İncele</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Oyuncu yükleme hatası:', err);
    }
}

/**
 * Ban oyuncu
 */
async function banPlayer(playerId) {
    if (!confirm(`${playerId} oyuncusunu banlamak istediğinize emin misiniz?`)) return;
    try {
        await VektiaAPI.banPlayer(playerId);
        showToast(`${playerId} banlandı`, 'success');
        loadAlerts();
        loadDashboard();
    } catch (err) {
        showToast(`Ban hatası: ${err.message}`, 'error');
    }
}

/**
 * Whitelist oyuncu
 */
async function whitelistPlayer(playerId) {
    try {
        await VektiaAPI.whitelistPlayer(playerId);
        showToast(`${playerId} beyaz listeye alındı`, 'success');
        loadAlerts();
    } catch (err) {
        showToast(`Hata: ${err.message}`, 'error');
    }
}

/**
 * Oyuncu Detay Modalını Aç
 */
async function openPlayerModal(playerId) {
    const modal = document.getElementById('playerModal');
    if (!modal) return;
    
    // Yükleniyor durumu
    document.getElementById('modalPlayerId').textContent = playerId;
    document.getElementById('modalPlayerStatus').innerHTML = '<span class="spinner"></span>';
    modal.showModal();
    
    try {
        const p = await VektiaAPI.getPlayer(playerId);
        
        document.getElementById('modalPlayerStatus').innerHTML = statusBadge(p.status) + ' ' + statusBadge(p.risk_level);
        document.getElementById('modalRiskScore').innerHTML = riskScoreBar(p.risk_score);
        document.getElementById('modalTotalEvents').textContent = formatNumber(p.total_events || 0);
        document.getElementById('modalLastSeen').textContent = timeAgo(p.last_seen);
        
        // ML & Stats details
        document.getElementById('modalStdDev').textContent = p.std_deviation ? p.std_deviation.toFixed(6) : 'N/A';
        
        if (p.ml_result) {
            document.getElementById('modalMLScore').textContent = parseFloat(p.ml_result.anomaly_score).toFixed(4);
            document.getElementById('modalMLRisk').textContent = p.ml_result.risk_level;
        } else {
            document.getElementById('modalMLScore').textContent = 'Analiz Yok';
            document.getElementById('modalMLRisk').textContent = '—';
        }
        
    } catch (err) {
        console.error(err);
        document.getElementById('modalPlayerStatus').textContent = 'Yüklenemedi';
    }
}

function closePlayerModal() {
    const modal = document.getElementById('playerModal');
    if (modal) modal.close();
}

// === Helpers ===

function setStatValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatNumber(num) {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return String(num);
}

function updateAlertBadge(count) {
    const badge = document.getElementById('alertBadge');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
    }
}

function showToast(message, type = 'info') {
    // Basit toast notification
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 24px; right: 24px; z-index: 300;
        padding: 12px 20px; border-radius: 10px;
        font-size: 0.85rem; font-weight: 500; font-family: Inter, sans-serif;
        color: #fff; animation: slideIn 0.3s ease-out;
        background: ${type === 'success' ? '#00b368' : type === 'error' ? '#cc1a4a' : '#0099cc'};
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// === Navigation ===

function setActiveNav(page) {
    const urlParams = new URLSearchParams(window.location.search);
    const clientId = urlParams.get('client_id');
    const query = clientId ? `?client_id=${clientId}` : '';

    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
        
        // Müşteriler (clients) sekmesi hariç diğer tüm linklere client_id ekle
        if (clientId && item.dataset.page !== 'clients' && item.dataset.page !== 'settings') {
            const baseHref = item.getAttribute('href').split('?')[0];
            item.setAttribute('href', baseHref + query);
        }
    });

    if (clientId) {
        const titleEl = document.querySelector('.header-title');
        if (titleEl) {
            titleEl.innerHTML += ` <span style="font-size: 0.9rem; color: var(--primary-color); background: rgba(0, 153, 204, 0.1); padding: 4px 8px; border-radius: 4px; vertical-align: middle; margin-left: 10px;">🔍 Filtre: Müşteri #${clientId}</span>`;
        }
    }
}
