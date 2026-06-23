/**
 * Vektia API Client
 * Tüm admin panel API iletişimini yönetir.
 */
const VektiaAPI = {
    baseUrl: window.location.origin,

    getToken() {
        return localStorage.getItem('vektia_token');
    },

    setToken(token) {
        localStorage.setItem('vektia_token', token);
    },

    clearToken() {
        localStorage.removeItem('vektia_token');
    },

    logout() {
        this.clearToken();
        window.location.href = 'login.html';
    },

    /**
     * Authenticated fetch wrapper
     */
    async request(endpoint, options = {}) {
        const token = this.getToken();
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                this.logout();
                throw new Error('Oturum süresi doldu');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (err) {
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
                throw new Error('Sunucuya bağlanılamıyor');
            }
            throw err;
        }
    },

    // === Auth ===
    async login(username, password) {
        return this.request('/api/v1/admin/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    },

    // URL'deki client_id parametresini oku
    getClientIdParam() {
        const urlParams = new URLSearchParams(window.location.search);
        const clientId = urlParams.get('client_id');
        return clientId ? `client_id=${clientId}` : '';
    },

    // Helper: Parametreleri birleştir
    buildQuery(paramsObj = {}) {
        const queryParams = new URLSearchParams(paramsObj);
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('client_id')) {
            queryParams.append('client_id', urlParams.get('client_id'));
        }
        const qs = queryParams.toString();
        return qs ? `?${qs}` : '';
    },

    // === Dashboard ===
    async getDashboard() {
        return this.request(`/api/v1/admin/dashboard${this.buildQuery()}`);
    },

    // === Players ===
    async getPlayers(params = {}) {
        return this.request(`/api/v1/admin/players${this.buildQuery(params)}`);
    },

    async getPlayer(playerId) {
        return this.request(`/api/v1/admin/players/${encodeURIComponent(playerId)}${this.buildQuery()}`);
    },

    async banPlayer(playerId, reason = 'Bot/Makro tespiti') {
        const urlParams = new URLSearchParams(window.location.search);
        const clientId = urlParams.get('client_id');
        if (!clientId) throw new Error('Ban işlemi için müşteri seçili olmalıdır');
        
        return this.request(`/api/v1/admin/players/${encodeURIComponent(playerId)}/ban?client_id=${clientId}`, {
            method: 'POST',
            body: JSON.stringify({ reason }),
        });
    },

    async whitelistPlayer(playerId, reason = 'False positive düzeltmesi') {
        const urlParams = new URLSearchParams(window.location.search);
        const clientId = urlParams.get('client_id');
        if (!clientId) throw new Error('İşlem için müşteri seçili olmalıdır');
        
        return this.request(`/api/v1/admin/players/${encodeURIComponent(playerId)}/whitelist?client_id=${clientId}`, {
            method: 'POST',
            body: JSON.stringify({ reason }),
        });
    },

    // === Alerts ===
    async getAlerts(limit = 50) {
        return this.request(`/api/v1/admin/alerts${this.buildQuery({limit})}`);
    },

    // === System Stats ===
    async getStats() {
        return this.request(`/api/v1/admin/stats`);
    },

    // === Client Management ===
    async createClient(data) {
        return this.request(`/api/v1/admin/clients`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    async updateClient(clientId, data) {
        return this.request(`/api/v1/admin/clients/${clientId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    async regenerateClientApiKey(clientId) {
        return this.request(`/api/v1/admin/clients/${clientId}/api_key`, {
            method: 'POST'
        });
    },

    async deleteClient(clientId) {
        return this.request(`/api/v1/admin/clients/${clientId}`, {
            method: 'DELETE'
        });
    },

    // === Health ===
    async getHealth() {
        return this.request('/api/v1/health');
    },
};

/**
 * Auth guard — giriş yapılmamışsa login'e yönlendir.
 * Login sayfasında çağırılmamalı.
 */
function requireAuth() {
    if (!VektiaAPI.getToken()) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}
