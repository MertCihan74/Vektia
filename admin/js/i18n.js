const i18n = {
    currentLang: localStorage.getItem('vektia_lang') || 'en',

    dict: {
        en: {
            "menu_dashboard": "Dashboard",
            "menu_users": "Users",
            "menu_settings": "Settings",
            "menu_billing": "Subscription",
            "menu_logout": "Logout",
            "title_dashboard": "Studio Dashboard",
            "title_users": "User Management",
            "title_billing": "Billing",
            "card_total_users": "Total Users",
            "card_active_users": "Active Users",
            "card_flagged_users": "Flagged",
            "card_banned_users": "Banned",
            "timeline_title": "Detection Timeline (Last Hour)",
            "alerts_title": "Recent Alerts",
            "filter_all": "All Users",
            "filter_most_events": "Most Events",
            "filter_high_risk": "High Risk Only",
            "filter_suspicious": "Suspicious Only",
            "filter_clean": "Clean Only",
            "filter_banned": "Banned Users",
            "btn_refresh": "Refresh",
            "th_user_id": "User ID",
            "th_risk_score": "Risk Score",
            "th_risk_level": "Risk Level",
            "th_total_events": "Total Events",
            "th_status": "Status",
            "btn_inspect": "Inspect",
            "loading": "Loading...",
            "no_users": "No users found.",
            "modal_action_premium": "Take action for this user (Premium Feature):",
            "modal_upgrade_msg": "🚫 Upgrade to Premium to take actions.",
            "btn_ban": "🚫 Ban",
            "btn_whitelist": "🤍 Whitelist",
            "msg_incidents_loading": "Loading incidents...",
            "msg_no_incidents": "No incidents found for this user.",
            "th_layer": "Layer",
            "th_date": "Date",
            "plan_premium": "Premium Plan ($99/Month)",
            "plan_free": "Free Trial",
            "status_active": "Active",
            "status_canceled": "Canceled",
            "status_past_due": "Past Due",
            "status_trial": "Trial Period",
            "btn_cancel_sub": "Cancel Subscription",
            "chart_clean": "Clean",
            "chart_low": "Low Risk",
            "chart_suspicious": "Suspicious",
            "chart_high": "High Risk",
            "chart_confirmed": "Confirmed Bot",
            "chart_flagged": "Flagged",
            "title_settings": "Settings",
            "premium_required": "Premium Feature",
            "premium_settings_desc": "You must upgrade to Premium to use auto-ban and advanced settings.",
            "btn_upgrade": "Upgrade",
            "protection_settings": "Protection Settings",
            "auto_ban_title": "Auto-Ban",
            "auto_ban_desc": "Automatically bans bots detected by AI without waiting.",
            "auto_ban_select": "Which risk levels should be auto-banned?",
            "risk_high": "High Risk (Confirmed Bot)",
            "risk_suspicious": "Suspicious",
            "btn_save": "Save"
        },
        tr: {
            "menu_dashboard": "Dashboard",
            "menu_users": "Kullanıcılar",
            "menu_settings": "Ayarlar",
            "menu_billing": "Üyelik Bilgilerim",
            "menu_logout": "Çıkış Yap",
            "title_dashboard": "Stüdyo Dashboard",
            "title_users": "Kullanıcı Yönetimi",
            "title_billing": "Fatura ve Abonelik",
            "card_total_users": "Toplam Kullanıcı",
            "card_active_users": "Aktif Kullanıcı",
            "card_flagged_users": "İşaretli",
            "card_banned_users": "Banlanan",
            "timeline_title": "Tespit Zaman Serisi (Son 1 Saat)",
            "alerts_title": "Son Uyarılar",
            "filter_all": "Tüm Kullanıcılar",
            "filter_most_events": "En Çok Vukuatı Olanlar",
            "filter_high_risk": "Sadece Yüksek Riskliler",
            "filter_suspicious": "Sadece Şüpheliler",
            "filter_clean": "Sadece Temizler",
            "filter_banned": "Banlı Kullanıcılar",
            "btn_refresh": "Yenile",
            "th_user_id": "Kullanıcı ID",
            "th_risk_score": "Risk Skoru",
            "th_risk_level": "Risk Seviyesi",
            "th_total_events": "Toplam Olay",
            "th_status": "Durum",
            "btn_inspect": "İncele",
            "loading": "Yükleniyor...",
            "no_users": "Kullanıcı bulunamadı.",
            "modal_action_premium": "Bu kullanıcı için aksiyon alın (Premium Özellik):",
            "modal_upgrade_msg": "🚫 Aksiyon almak için Premium pakete geçin.",
            "btn_ban": "🚫 Banla",
            "btn_whitelist": "🤍 Beyaz Listeye Al",
            "msg_incidents_loading": "Vukuatlar yükleniyor...",
            "msg_no_incidents": "Bu kullanıcıya ait herhangi bir vukuat bulunamadı.",
            "th_layer": "Katman",
            "th_date": "Tarih",
            "plan_premium": "Premium Paket ($99/Ay)",
            "plan_free": "Ücretsiz Deneme (Free)",
            "status_active": "Aktif",
            "status_canceled": "İptal Edildi",
            "status_past_due": "Ödeme Gecikti",
            "status_trial": "Deneme Sürümü",
            "btn_cancel_sub": "Aboneliği İptal Et",
            "chart_clean": "Temiz",
            "chart_low": "Düşük Risk",
            "chart_suspicious": "Şüpheli",
            "chart_high": "Yüksek Risk",
            "chart_confirmed": "Kesin Bot",
            "chart_flagged": "İşaretli",
            "title_settings": "Ayarlar",
            "premium_required": "Premium Özellik",
            "premium_settings_desc": "Otomatik engelleme ve gelişmiş ayarları kullanmak için Premium pakete geçiş yapmalısınız.",
            "btn_upgrade": "Yükselt",
            "protection_settings": "Koruma Ayarları",
            "auto_ban_title": "Otomatik Engelleme",
            "auto_ban_desc": "Yapay zeka tarafından tespit edilen botları beklemeden engeller.",
            "auto_ban_select": "Hangi seviyeler otomatik engellensin?",
            "risk_high": "Riskli (Kesin Bot)",
            "risk_suspicious": "Şüpheli",
            "btn_save": "Kaydet"
        }
    },

    setLang(lang) {
        if (this.dict[lang]) {
            this.currentLang = lang;
            localStorage.setItem('vektia_lang', lang);
            this.translatePage();
            
            // Dispatch event for other scripts
            window.dispatchEvent(new Event('languageChanged'));
        }
    },

    t(key) {
        return this.dict[this.currentLang][key] || key;
    },

    translatePage() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (this.dict[this.currentLang][key]) {
                if (el.tagName.toLowerCase() === 'input' && el.hasAttribute('placeholder')) {
                    el.setAttribute('placeholder', this.dict[this.currentLang][key]);
                } else {
                    el.innerHTML = this.dict[this.currentLang][key];
                }
            }
        });
        
        // Dil seçici UI güncellemesi
        const langSelect = document.getElementById('langSelect');
        if (langSelect) {
            langSelect.value = this.currentLang;
        }
    }
};

// Sayfa yüklendiğinde çevir
document.addEventListener('DOMContentLoaded', () => {
    i18n.translatePage();
});
