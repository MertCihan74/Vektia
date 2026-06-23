# Vektia B2B Onboarding ve Entegrasyon Süreci

Bu doküman, bir müşteri (Örn: E-Ticaret sitesi, Kripto Borsası veya Oyun Stüdyosu) ile anlaştıktan sonra, Vektia'yı onların sistemine nasıl entegre edeceğinizi adım adım açıklamaktadır. 

---

## 1. Satış Sonrası Süreç (Kim Ne Yapacak?)

### Adım 1: Hesap Açılışı (Bizim Tarafımız)
1. Müşteriye özel bir **Vektia Müşteri Hesabı** oluşturulur.
2. Bu hesaba bağlı, benzersiz bir `API_KEY` üretilir.
3. Müşteriye Vektia'nın Müşteri Paneli giriş bilgileri, API anahtarı ve Entegrasyon Dokümanı gönderilir.

### Adım 2: Backend Entegrasyonu (Müşteri Tarafı)
Müşterinin yazılım ekibi, kendi backend (sunucu) kodlarına Vektia'yı entegre eder:
1. İlgili aksiyon fonksiyonunu (Örn: `ProcessCheckout`, `PlaceTradeOrder`, veya `PlayerAttack`) bulur.
2. Bu aksiyon gerçekleştiğinde Vektia'nın `https://api.vektia.io/api/v1/telemetry/event` adresine HTTP POST atacak asenkron (fire-and-forget) bir kod ekler. Header kısmında `API_KEY` yollanır.
3. Kodu test ortamında çalıştırır.

**Örnek Veri Şeması (Dinamik Payload):**
```json
{
  "user_id": "usr_9921",
  "action_type": "checkout_click",
  "timestamp": 17182930192,
  "metadata": {
     "ip_address": "192.168.1.1",
     "user_agent": "Mozilla/5.0..."
  }
}
```

### Adım 3: PoC (Proof of Concept) ve Gölge Modu (Ortak Süreç)
1. Müşteri veriyi göndermeye başlar.
2. Kendi Müşteri Paneli üzerinden verilerin başarıyla aktığını (Dashboard'daki grafikleri) kendi gözüyle görür.
3. **ÖNEMLİ:** İlk 1 hafta Vektia **Gölge Modunda (Shadow Mode)** çalıştırılır. Yani Vektia botları tespit eder, panele loglar ama müşterinin sunucusuna "Engelle" (Webhook) komutu GÖNDERMEZ.
4. 1 haftanın sonunda müşteriyle durum değerlendirmesi yapılır. Panele girilip "Bakın, sisteminizdeki şu 150 bot saniyede 10 kere form dolduruyor" diyerek sahte trafik kanıtlanır.

### Adım 4: Canlıya Alma ve Webhook Bağlantısı (Son Aşama)
1. Müşteri yakalanan botları görüp ikna olur.
2. Müşteri kendi sunucusunda bir **Aksiyon Endpoint'i** (Örn: `/api/block-user`) oluşturur ve bu URL'yi Vektia paneline "Webhook URL" olarak kaydeder.
3. Vektia'nın Gölge Modu kapatılır, **Aktif Koruma Moduna** geçirilir. Vektia bot gördüğü an müşterinin URL'sine sinyal atıp botun oturumunu sonlandırır veya işlemi reddeder.
4. Faturalandırma (Stripe vb. üzerinden) başlatılır.

---

## 2. Sistemin Teknik Gereksinimleri

Vektia'nın çok kiracılı (Multi-Tenant) yapısı şu temel bileşenlere dayanır:

1. **API Key ve Rate Limit Yönetimi:**
   Veritabanında her müşterinin kendi API anahtarı ve saniyelik kota limiti (rate_limit) bulunur. Sistem aşırı yükü engellemek için müşteri bazlı sınırlamalar yapar.

2. **İzole Paneller (Süper Admin vs Müşteri):**
   - **Süper Admin Paneli:** Vektia yöneticileri, platforma bağlı tüm e-ticaret siteleri, borsalar ve oyunların "toplam" sağlığını, aktif müşteri sayısını ve kümülatif grafikleri izler.
   - **Müşteri Paneli:** Müşteri giriş yaptığında *SADECE kendi gönderdiği `client_id`'ye ait kullanıcıları* ve risk grafiklerini görebilir. Veri sızıntısı imkansızdır.

3. **Dinamik Webhook (Geri Bildirim Servisi):**
   Her müşterinin kendi `webhook_url` değeri veritabanında tutulur. Vektia AI Worker modülü, hileyi veya botu tespit ettiğinde hangi müşterinin kullanıcısıysa, gidip o müşterinin kayıtlı URL'sine POST atarak engelleme komutu verir.
