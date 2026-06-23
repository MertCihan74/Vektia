# Vektia: Ürün Stratejisi, Ölçeklenebilirlik ve Pazarlama Planı

Vektia, istemci tabanlı (client-side) güvenlik sistemlerinin aksine, tamamen **sunucu tabanlı (server-side)** ve **davranışsal analize** dayanan yeni nesil bir B2B SaaS çözümüdür. İlk aşamada oyun hile koruması olarak tasarlanan Vektia, temelinde "insan vs. robotik davranış ayrımı" yattığı için **Genel B2B Davranışsal Güvenlik ve Anti-Bot Platformu** olarak konumlandırılmaktadır.

Bu dokümanda Vektia'nın ticari bir ürüne dönüştüğünde pazar payını nasıl artıracağını, performans limitlerini ve pazarlama stratejisini inceleyeceğiz.

---

## 1. SaaS Mimarisi: Multi-Tenancy (Çok Kiracılılık)

Vektia'yı bir SaaS (Hizmet olarak Yazılım) modeliyle sunduğunuzda sistem **Multi-Tenant** mimaride çalışacak:

* **Müşteri İzolasyonu:** E-ticaret platformları, kripto borsaları veya oyun stüdyolarına özel bir `API_KEY` atanır.
* **Müşteri Paneli:** Müşterileriniz Admin Paneline girdiklerinde, sadece **kendi API anahtarlarıyla** eşleşen verileri görürler. Vektia yöneticileri (Süper Admin) ise platformu kullanan *tüm müşterilerin* toplam sağlığını ve özetlerini tek potada görebilir.
* **Webhook Entegrasyonu:** Vektia bir bot tespit ettiğinde doğrudan müşterinin sunucusuna webhook fırlatır ve bot anında bloklanır veya oturumu sonlandırılır.

## 2. Ölçeklenebilirlik: Kaç İşlemi Analiz Edebilir?

Vektia'nın farkı **Katmanlı Elek Mimarisi (Layered Sieve)** kullanmasıdır.

### Performans Testleri ve Beklentiler
* **Katman 1 (Redis Sliding Window):** Redis, saniyede **100,000+ okuma/yazma** işlemini rahatlıkla yapabilir. Saniyede binlerce form doldurma veya tıklama işlemi Vektia tarafından sadece %10 Redis CPU kullanımıyla tutulur.
* **Katman 2 (İstatistik Filtresi):** Zaman karmaşıklığı O(N)'dir. Sadece Sliding Window dolduğunda çalışır.
* **Katman 3 (Isolation Forest ML):** En ağır işlemdir, ancak Katman 1 ve 2 verinin **%95'ini temiz** bularak eler. Yapay zekaya devasa veri değil, sadece şüpheli bulunan spesifik veriler asenkron olarak gider.

**Sonuç:** Tek bir standart sunucuda Vektia, eş zamanlı milyonlarca isteği rahatlıkla, milisaniyelik gecikmelerle analiz edebilir.

---

## 3. Pazarlama Stratejisi ve USP (Unique Selling Proposition)

### Neyi Satıyoruz? Vektia'nın Avantajları:

1. **Son Kullanıcının Cihazına Sızmaz (Privacy-First):**
   * *Diğerleri:* Mobil cihazlara veya bilgisayarlara SDK/Kernel kurmayı zorunlu tutar. Performansı düşürür ve veri gizliliği (GDPR) sorunları yaratır.
   * **Vektia:** Kullanıcının cihazına **HİÇBİR ŞEY** kurulmaz. Her şey müşterinin backend sunucusundan Vektia'ya gelen telemetri ile uzaktan analiz edilir. 

2. **Geliştirmesi Biten Projelere Sonradan (Tak-Çalıştır) Eklenebilir:**
   * **Vektia:** Sistemlere entegre olması sadece tek satırlık bir HTTP POST isteği (`/api/v1/telemetry/event`) eklemek kadar kolaydır. 1 saat içinde yayına alınır.

3. **Makro, Arbitraj ve Sneaker Botlarını Yakalar:**
   * CAPTCHA veya IP banlama gibi eski yöntemler gelişmiş botları durduramaz. Vektia kullanıcının **davranış paternine** (tıklama aralıklarındaki standart sapma, milisaniyelik gecikmeler, ritmik tutarlılık) baktığı için robotik hareket eden hiçbir yazılım kaçamaz.

### Hangi Sektörlere Satılmalı? (Hedef Kitle)
* **E-Ticaret ve Bilet Platformları:** Stokları saniyeler içinde tüketen "Sneaker Bot" veya bilet karaborsacı botlarını durdurmak.
* **FinTech & Kripto Borsaları:** Normal bir insanın yapamayacağı hızda API veya arayüz üzerinden işlem yapan otomatik arbitraj botlarını tespit etmek.
* **Sosyal Medya ve Reklam Ağları (Ad-Click Fraud):** Sitelere scraping (veri kazıma) yapan botlar veya sahte reklam tıklamaları yapan farm'lar.
* **Oyun Stüdyoları (MMORPG / Indie / Mobil):** Maden/balık botları veya makrolar kullanan oyuncuların Kernel seviyesinde izin istemeden tespit edilmesi.

### İş Modeli (Fiyatlandırma)
* **Kullandığın Kadar Öde (Pay-as-you-go):** Analiz edilen işlem (event) sayısı başına ücretlendirme. (Örn: Her 1 Milyon Telemetri Event'i için $5).
* **Abonelik:** "Start-up Plan" (Aylık $99), "Enterprise" (Aylık $999+).

---

## 4. Satış Başucu Rehberi (Sales Playbook)

### Söylemler (Satış Cümleleri)
* *"Kullanıcılarınıza CAPTCHA çözdürmekten vazgeçin; dönüşüm (conversion) oranlarınızı düşürmeyin. Biz botları arka planda sezsizce engelleriz."*
* *"GDPR uyumlu, cihaz-bağımsız (agentless) güvenlik. Kullanıcınızın cihazına değil, davranışına odaklanıyoruz."*
* *"Sahte trafikleri ve stok tüketen makroları makine öğrenmesiyle sıfır hata payıyla ayıklayın."*

### Satışı Kapatma Taktiği: Gölge Modu (Shadow Mode)
Firmalara yaklaşırken **PoC (Proof of Concept)** sunulmalıdır:
> "Bize 1 haftalık ücretsiz deneme şansı verin. Vektia'yı backendinize bağlayalım, kimseyi engellemeyelim (Sadece İzleme Modu). 1 hafta sonra size sitenizde işlem yapan gizli botların ve sahte trafiğin raporunu sunalım."
Müşteri raporu gördüğünde, bizzat manuel olarak fark edemediği sızıntıları anladığında sistemi satın alacaktır.
