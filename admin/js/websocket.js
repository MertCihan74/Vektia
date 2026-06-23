/**
 * Vektia WebSocket Manager
 * Admin paneline canlı uyarı akışı sağlar.
 */
class VektiaWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
        this.listeners = new Map();
        this.isConnected = false;
    }

    /**
     * Admin live feed'e bağlan
     */
    connect() {
        const token = VektiaAPI.getToken();
        if (!token) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/api/v1/admin/live`;

        try {
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                // Auth mesajı gönder
                this.ws.send(JSON.stringify({ token }));
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.status === 'authenticated') {
                        this.isConnected = true;
                        this.reconnectAttempts = 0;
                        this._emit('connected', data);
                        this._updateStatusDot('online');
                        return;
                    }

                    if (data.error) {
                        console.error('WS Error:', data.error);
                        this._emit('error', data);
                        return;
                    }

                    // Canlı uyarı
                    this._emit('alert', data);
                } catch (e) {
                    console.error('WS parse error:', e);
                }
            };

            this.ws.onclose = () => {
                this.isConnected = false;
                this._updateStatusDot('offline');
                this._emit('disconnected');
                this._tryReconnect();
            };

            this.ws.onerror = (err) => {
                console.error('WS error:', err);
                this._updateStatusDot('degraded');
            };
        } catch (e) {
            console.error('WS connection failed:', e);
        }
    }

    disconnect() {
        this.reconnectAttempts = this.maxReconnectAttempts; // Reconnect'i durdur
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Event listener ekle
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    _emit(event, data) {
        const callbacks = this.listeners.get(event) || [];
        callbacks.forEach(cb => cb(data));
    }

    _tryReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);

        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    }

    _updateStatusDot(status) {
        const dot = document.querySelector('.status-dot');
        if (dot) {
            dot.className = `status-dot ${status}`;
        }
        const label = document.querySelector('.status-label');
        if (label) {
            const labels = { online: 'Çevrimiçi', offline: 'Çevrimdışı', degraded: 'Sorunlu' };
            label.textContent = labels[status] || status;
        }
    }
}

// Global instance
const vektiaWS = new VektiaWebSocket();
