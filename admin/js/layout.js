/**
 * layout.js
 * Common layout components (Sidebar, Top Navigation)
 */

function renderCustomerSidebar(activeId) {
    const sidebarHtml = `
        <div class="sidebar-header">
            <div class="sidebar-logo">
                <div class="logo-icon">V</div>
                <span class="logo-text">Vektia</span>
                <span class="badge" id="tierBadge" style="margin-left:auto; font-size:0.7rem;"></span>
            </div>
        </div>
        
        <div style="padding: 1rem; color: var(--primary-color); font-weight: 500; border-bottom: 1px solid var(--border-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" id="clientNameDisplay">
            Yükleniyor...
        </div>

        <nav class="sidebar-nav">
            <div class="nav-section-label">Stüdyo Menüsü</div>
            <a href="customer.html" class="nav-item ${activeId === 'dashboard' ? 'active' : ''}">
                <span class="nav-icon">📊</span>
                <span data-i18n="menu_dashboard">Dashboard</span>
            </a>
            <a href="customer_players.html" class="nav-item ${activeId === 'players' ? 'active' : ''}">
                <span class="nav-icon">👥</span>
                <span data-i18n="menu_users">Kullanıcılar</span>
            </a>
            <a href="customer_billing.html" class="nav-item ${activeId === 'billing' ? 'active' : ''}">
                <span class="nav-icon">💳</span>
                <span data-i18n="menu_billing">Üyelik Bilgilerim</span>
            </a>
            <a href="customer_settings.html" class="nav-item ${activeId === 'settings' ? 'active' : ''}">
                <span class="nav-icon">⚙️</span>
                <span data-i18n="menu_settings">Ayarlar</span>
            </a>
        </nav>

        <div class="sidebar-footer">
            <button class="btn btn-ghost" style="width: 100%; text-align: left; display: flex; align-items: center; gap: 0.5rem;" onclick="logoutCustomer()">
                🚪 <span data-i18n="menu_logout">Çıkış Yap</span>
            </button>
        </div>
    `;

    document.getElementById('sidebar-container').innerHTML = sidebarHtml;
    
    // If i18n is available, refresh translation
    if (window.i18n && typeof window.i18n.applyTranslations === 'function') {
        window.i18n.applyTranslations();
    }
}

function renderAdminSidebar(activeId) {
    const sidebarHtml = `
        <div class="sidebar-header">
            <div class="sidebar-logo">
                <div class="logo-icon">V</div>
                <span class="logo-text">Vektia</span>
                <span class="logo-badge">v0.1</span>
            </div>
        </div>

        <nav class="sidebar-nav">
            <div class="nav-section-label">Ana Menü</div>
            <a href="index.html" class="nav-item ${activeId === 'dashboard' ? 'active' : ''}">
                <span class="nav-icon">📊</span>
                Dashboard
            </a>
            <a href="clients.html" class="nav-item ${activeId === 'clients' ? 'active' : ''}">
                <span class="nav-icon">🏢</span>
                Müşteriler
            </a>
            
            <div class="nav-section-label">Sistem</div>
            <a href="settings.html" class="nav-item ${activeId === 'settings' ? 'active' : ''}">
                <span class="nav-icon">⚙️</span>
                Ayarlar
            </a>
        </nav>

        <div class="sidebar-footer">
            <div class="user-info">
                <div class="user-avatar">A</div>
                <div class="user-details">
                    <div class="user-name" id="adminName">Admin</div>
                    <div class="user-role">Yönetici</div>
                </div>
                <button class="btn btn-ghost btn-sm" onclick="VektiaAPI.logout()" title="Çıkış Yap">🚪</button>
            </div>
        </div>
    `;

    document.getElementById('sidebar-container').innerHTML = sidebarHtml;
}

// Helper to load admin name if token exists
function loadAdminInfo() {
    const token = localStorage.getItem('vektia_token');
    if (token) {
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const adminNameEl = document.getElementById('adminName');
            if (adminNameEl && payload.sub) {
                adminNameEl.textContent = payload.sub;
            }
        } catch(e) {}
    }
}
