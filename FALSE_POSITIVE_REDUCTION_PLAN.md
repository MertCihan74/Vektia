# Vektia — Yanlış Pozitif (False Positive) Azaltma Planı

**Hedef:** Gerçek oyuncuların yanlışlıkla bot/makro olarak işaretlenmesini minimuma indirmek.
**Felsefe:** Bir gerçek oyuncuyu yanlışlıkla cezalandırmaktansa, bazı botları kaçırmayı kabul ederiz (precision > recall). Anti-cheat'te yanlış ban, doğru ban'dan çok daha pahalıdır (müşteri kaybı, itibar, destek yükü).

---

## 📍 GÜNCEL DURUM (2026-06-24)

Faz 0, 1 ve 2'nin büyük kısmı **kodda uygulandı** (working tree'de, henüz commit edilmedi).
Kanıt için `git diff` ve `CLAUDE.md`'ye bak. Kalanlar Faz 3 ve Faz 4.

| Faz | Durum | Not |
|---|---|---|
| **Faz 0** — Doğruluk temeli | ✅ Yapıldı | `ActionType`/`Vector3` importları eklendi; tüm eşikler **ms**'e taşındı (`config.py`, `layer2_stats.py`); `MIN_DELTA_MS=1.0` veri hijyeni eklendi. |
| **Faz 1** — Tek pencere kararını kaldır | ✅ Yapıldı | `temporal.py` (söndürmeli kanıt skoru) + pipeline entegrasyonu. Tek HIGH pencere asla CONFIRMED üretmez (`tests/test_temporal.py` bunu sabitliyor). |
| **Faz 2** — Hard kuralları ML'e bağla | ✅ Büyük ölçüde | `layer3_ml.py:117` kısayolu kaldırıldı; ML her şüpheli için çalışır ve güvenlik ağıdır. range_ratio 1.05→1.03, autocorrelation 0.70→0.80, spatial 1.10→1.03 ayarlandı. **Kalan:** hard `return 1.0` blokları hâlâ var (temporal süzdüğü için kabul edilebilir, ama Faz 3'le birlikte sinyale çevrilebilir). |
| **Faz 3** — Per-player baseline & whitelist | ✅ Büyük ölçüde | `baseline.py` (per-player trust EMA → leniency); pipeline'da whitelist enforcement (eskiden eksikti) + temporal reset. `temporal_confirm_threshold` 2.5→1.9 (2.5=asimptot, ulaşılamazdı). **Kalan:** per-player baseline-deviation (davranış-değişimi tespiti), whitelist için panel akışı testi. |
| **Faz 4** — Ölçüm & kalibrasyon | ◐ Kısmen | Shadow mod (`VEKTIA_SHADOW_MODE`) + `false_positive_rate` beslemesi (`metrics.py`) eklendi. **Kalan:** müşteri-bazlı eşik override, gerçek trafikte eski-vs-yeni A/B raporu, `ANOMALY_SLOPE` kalibrasyonu. |

**⚠️ Kritik bağımlılık:** Faz 2'nin ML güvenlik ağı **yalnızca model eğitilmişse** çalışır.
`layer3_ml.predict()` model eğitilmemişse L2 skorunu aynen döndürür → HIGH, HIGH kalır.
`models/isolation_forest.joblib` üretilmeli (`train_model.py` + `generate_mock_data.py`).
Bu yüzden **"model eğitimi" Faz 3'ten önce gelen bir P0 görevidir.**

> Aşağıdaki orijinal analiz, kararların *neden* böyle alındığını belgeler — referans olarak korunur.

---

## 1. Yanlış Pozitif Üreten Asıl Mekanizma

Tüm sorunların kaynağı tek bir mimari karar: **Katman 2'deki "hard limit" kuralları tek bir 20'lik pencerede (`max_window=20`, yani 19 delta) anında `risk_score = 1.0 / RiskLevel.HIGH` döndürüyor; bu da Katman 3'te (`layer3_ml.py`) doğrudan `CONFIRMED`'e çevriliyor ve ML kontrolünü (güvenlik ağını) tamamen atlıyor.**

Yani en kırılgan, en küçük örneklemli kararlar, en sert ve en temyiz edilemez cezayı veriyor. Asıl çelişki bu.

İlgili kanıt:
- `layer2_stats.py` → `_evaluate_risk` içindeki erken `return 1.0, RiskLevel.HIGH` blokları.
- `layer3_ml.py:117` → `if stats_result.risk_score == 1.0: combined_score = 1.0; risk_level = CONFIRMED` (ML hiç çalışmaz).

---

## 2. Kod Kanıtlı Yanlış Pozitif Kaynakları

| # | Konum (layer2_stats.py) | Kural | Neden gerçek oyuncuyu vurur |
|---|---|---|---|
| FP-1 | satır ~238 | `range_ratio < 1.05` → anında HIGH | 19 deltalık küçük örneklemde, ritmik/yetenekli bir oyuncu şans eseri çok dar aralığa düşebilir. Tek bir kural, tek pencere, temyizsiz ban. |
| FP-2 | satır ~243 | `mean_delta < 0.035 veya median_delta < 0.035` (>28 CPS) | Drag-click / jitter-click yapan yetenekli oyuncular kısa burst'lerde bu eşiği geçebilir. Ayrıca **birim tutarsızlığı** (bkz. §3) bu eşiği tümüyle anlamsız kılabilir. |
| FP-3 | satır ~248 | `mean_delta < 0.060 ve cv < 0.10` (16+ CPS, %10 altı sapma) | İyi bir drag-click'çi yüksek hızda düşük sapma üretebilir. |
| FP-4 | satır ~254 | `autocorrelation > 0.70` → anında HIGH | **Otokorelasyon 19 örnekte istatistiksel olarak güvenilmez.** Yarı-periyodik insan tıklaması rastgele biçimde 0.70'i aşabilir (özellikle `max_lag=5` ile birden çok lag denenip en yükseği alınınca — "max seçme" yanlılığı pozitifi şişirir). |
| FP-5 | satır ~223 | Spatial jitter: `std_x==0 ve std_y==0` + (`cv<0.05` veya `range_ratio<1.10`) | Köşe tutan (angle-holding) ve fareyi sabit tutup düzenli tıklayan oyuncu, koordinat gönderen oyunlarda yakalanır. README bu senaryoyu "serbest" sayacağını iddia ediyor ama `range_ratio<1.10` eşiği insan için fazla dar. |
| FP-6 | (tasarım) | Tüm hard kurallar **tek pencerede** karar verir | Tek bir şanssız pencere = anında flag. Zaman içinde tekrar/ısrar koşulu yok. |
| FP-7 | (tasarım) | Hard kurallar **ML'i atlar** | Sistemin asıl "akıllı" katmanı (Isolation Forest) yalnızca zaten yakalanmamışları görüyor; kırılgan kararlar denetlenmeden ban'a gidiyor. |

---

## 3. Doğruluğu Baştan Bozan Çapraz Konular

Bunlar düzeltilmeden eşik ayarı yapmak anlamsız — çünkü modelin gördüğü sayılar belirsiz.

**3a. Birim tutarsızlığı (kritik).**
`TELEMETRY_DATA_FORMAT.md` ve `models.py`, `timestamp`'i **milisaniye** olarak tanımlıyor (örn. `1719129600550`, FiveM `GetGameTimer()`). Ancak `layer2_stats.py` eşikleri açıkça **saniye** varsayıyor (`mean_delta < 0.035` = 35ms, `mean_delta < 0.010` = 10ms) ve `config.py`'deki `bot_threshold=0.005`, `suspicious_threshold=0.05` da saniye cinsinden.
- Müşteri ms gönderirse: delta'lar ~100 gibi olur, hiçbir zaman 0.035'in altına inmez → kurallar hiç tetiklenmez (**yanlış negatif**), std büyük çıkar → her şey CLEAN.
- Müşteri saniye gönderirse: kurallar çalışır ama dökümantasyonla çelişir.
- Müşteriler arası tutarsızlık → öngörülemez davranış, hem FP hem FN.
**Yapılacak:** Ingest anında tek bir kanonik birim (ms öneriyoruz, dökümana uygun) belirle ve tüm delta/eşik hesabını ona göre normalize et. Tüm eşikleri bu birime taşı.

**3b. Çalışma-zamanı hataları (P0 — sistem düzgün çalışmıyor).**
Statik analizle doğrulandı:
- `layer2_stats.py`, `ActionType`'ı **import etmiyor** ama `_evaluate_risk` imzasında ve gövdesinde (`ActionType.CLICK`, `ActionType.MOVE`) kullanıyor → import anında `NameError`. `from __future__ import annotations` da yok.
- `layer1_redis.py`, ana `process()` yolunda `Vector3` kullanıyor ama import etmiyor → bu kod yolunda `NameError`.
Bu hatalar düzeltilmeden FP ölçümü yapılamaz; çünkü bahsedilen "sol tıkta bot işaretleme" davranışı muhtemelen yalnızca fallback yollarında veya kısmen çalışan kod üzerinde gözlemleniyor.

**3c. Veri hijyeni.**
Tek filtre `deltas > 0`. Ağ tekrarı (resend), batch sıkışması, istemci saat sıçraması veya lag-spike sonrası "yetişme" paketleri delta'ları yapay olarak sıkıştırıp düşük varyans → sahte "bot" üretir. Aykırı-değer ve makul-aralık (örn. 5ms–10s) filtresi yok.

---

## 4. Çözüm Yol Haritası (Fazlı)

### Faz 0 — Doğruluk temeli (P0, önkoşul)
1. `layer2_stats.py`'ye `ActionType` importunu, `layer1_redis.py`'ye `Vector3` importunu ekle. Pipeline'ın gerçekten uçtan uca çalıştığını bir entegrasyon testiyle doğrula.
2. Birim normalizasyonu: ingest'te timestamp'i kanonik birime (ms) çevir; tüm eşikleri ms cinsine taşı ve `config.py`'de tek yerde tut.
3. Veri hijyeni: delta'lara makul-aralık filtresi (örn. `5ms < delta < 10s`) ve duplicate/aykırı temizliği ekle.

### Faz 1 — Tek pencere kararını kaldır: "kanıt biriktirme"
Asıl FP ilacı. Tek bir pencere asla ban/confirmed üretmemeli.
1. **Çoklu-pencere ısrar koşulu (persistence):** Bir oyuncu CONFIRMED'e ancak *art arda K bağımsız pencerede* (örn. K=3) yüksek risk üretirse gitsin. Tek seferlik şüphe yalnızca "izlemeye al" durumunu tetiklesin.
2. **Kayan kanıt skoru / decay:** Oyuncu başına zamanla artıp temiz pencerelerde azalan bir "şüphe puanı" tut (Redis'te). Ban eşiği bu birikmiş puana bağlansın, anlık pencereye değil.
3. **Örneklem boyutu kapısı:** `max_window`'u istatistik için yükselt (örn. 20 → 40–50) veya hard kuralları yalnızca pencere doluyken + minimum delta sayısı sağlanınca uygula. Küçük örneklemde sert iddia yok.

### Faz 2 — Hard kuralları yumuşat ve ML'e bağla
Amaç: hiçbir tek heuristik tek başına `CONFIRMED` üretmesin; hepsi ML'in göreceği "şüphe" sinyaline dönüşsün.
1. **Hard `return 1.0` bloklarını kaldır/indir:** FP-1…FP-5 kurallarını anında-ban yerine **skorlu sinyale** çevir (ağırlıklı toplama besle). Yalnızca fizyolojik olarak imkânsız + tekrar eden durumlar (örn. *varyans tam 0* ve *çoklu pencerede sabit*) doğrudan yüksek risk olabilir.
2. **`range_ratio < 1.05` (FP-1):** eşiği düşür/insanileştir ve tek başına ban yapma; sinyal olarak kullan.
3. **`autocorrelation > 0.70` (FP-4):** (a) eşiği yükselt, (b) "max lag seçme" yanlılığını düzelt (her lag'i tek tek karar vermek yerine, lag'leri istatistiksel anlamlılıkla değerlendir), (c) küçük örneklemde otokorelasyona güvenme — daha büyük pencere iste.
4. **Spatial jitter (FP-5):** `range_ratio<1.10` eşiğini gevşet; "0 piksel + kötü ritim = insan (köşe tutma)" istisnasını genişlet.
5. **`layer3_ml.py:117`:** `risk_score==1.0 → CONFIRMED` kısayolunu kaldır veya yalnızca Faz-1 ısrar koşulu sağlandığında uygula. ML her şüpheli için gerçekten çalışsın.

### Faz 3 — Per-player baseline & whitelist
1. **Oyuncu temel çizgisi (baseline):** Her oyuncunun kendi geçmiş ritim dağılımına göre değerlendir; "bu oyuncu için anormal mi?" sorusu, global eşikten daha az FP üretir.
2. **Whitelist / güven seviyeleri:** Uzun süredir temiz, yüksek hacimli oyuncular için daha toleranslı eşik; yeni/şüpheli hesaplar için normal. `BanStatus.WHITELISTED` zaten modelde var, mekanizmayı bağla.
3. **İnsan-onayı varsayılanı:** `auto_ban_enabled=False`, `ban_requires_admin_approval=True` zaten iyi; bunu güçlü varsayılan olarak koru ve panelde "şüpheli ama otomatik banlanmadı" akışını öne çıkar.

### Faz 4 — Ölçüm, kalibrasyon, geri besleme
1. **FP telemetrisi:** `DashboardStats.false_positive_rate` alanı var ama beslenmiyor. Admin'in "yanlış işaretlendi" geri bildirimini topla ve eşikleri buna göre kalibre et.
2. **Gölge mod (shadow mode):** Yeni eşikleri canlıda ban yapmadan logla; gerçek FP/FN oranını ölç, sonra devreye al.
3. **Eşikleri konfigüre edilebilir yap:** Her müşteri/oyun tipi (rhythm game vs. survival) farklı; eşikler `config.py` + müşteri bazlı override ile ayarlanabilir olsun.

---

## 5. Önerilen Parametre Değişiklikleri (kalibrasyonla netleşecek başlangıç değerleri)

| Parametre | Mevcut | Öneri | Gerekçe |
|---|---|---|---|
| `max_window` | 20 | 40–50 | Daha büyük örneklem = daha güvenilir istatistik, daha az şans eseri FP. |
| Tek pencere → CONFIRMED | var | **kaldır** | En büyük FP kaynağı. K=3 ardışık pencere iste. |
| `range_ratio < 1.05` hard-ban | var | sinyale çevir | Tek başına ban yapma. |
| `autocorrelation > 0.70` hard-ban | var | ≥0.85 + büyük örneklem + sinyal | Küçük örneklem otokorelasyonu güvenilmez. |
| `mean_delta` eşikleri | saniye (0.035 vb.) | ms'e normalize | Birim tutarsızlığını gider. |
| Spatial `range_ratio < 1.10` | var | gevşet | Köşe tutan insanı koru. |
| `risk_score==1.0` → CONFIRMED (layer3) | var | ısrar koşuluna bağla | ML güvenlik ağını çalıştır. |

> Not: Bu değerler kesin değil; Faz 4'teki gölge mod ölçümleriyle kalibre edilmeli.

---

## 6. Doğrulama / Test Planı

1. **Birim testleri:** Her heuristik için "insan benzeri" (yüksek sapmalı) ve "bot benzeri" (sıfır sapmalı) sentetik pencerelerle FP/FN davranışını sabitle. `generate_mock_data.py` genişletilebilir.
2. **FP regresyon seti:** Bilinen gerçek-oyuncu kayıtlarından (rhythm gamer, drag-clicker, köşe tutan) oluşan bir set; hiçbiri CONFIRMED olmamalı.
3. **FN kontrol seti:** Bilinen makro/auto-clicker kalıpları hâlâ yakalanmalı (recall'u tümden kaybetmediğimizi doğrula).
4. **Gölge mod karşılaştırması:** Eski vs. yeni kuralların aynı trafikte ürettiği flag farkını raporla.
5. **Yük testi:** Pencere büyütmenin (40–50) Redis RAM ve gecikme etkisini ölç.

---

## 7. Özet — Sıralı Aksiyon

1. **Faz 0:** Import hatalarını düzelt + birim normalize et + veri hijyeni. (Sistemi gerçekten çalışır ve ölçülebilir yap.)
2. **Faz 1:** Tek pencere kararını kaldır → çoklu-pencere ısrar + biriken şüphe puanı. (En büyük FP düşüşü burada.)
3. **Faz 2:** Hard kuralları sinyale çevir, ML'i her şüpheli için çalıştır.
4. **Faz 3:** Per-player baseline + whitelist + insan onayı.
5. **Faz 4:** Gölge modda ölç, FP oranını besle, eşikleri kalibre et.

---

## 8. KALAN İŞ — Sıradaki Somut Adımlar (2026-06-24 itibarıyla)

Faz 0–2 kodda. "Ritmik sol-tık → bot" senaryosu için bugünkü savunma zinciri:
`tek pencere HIGH değil → temporal ~3 ardışık HIGH ister → ML güvenlik ağı normal derse confirmed yok → auto_ban kapalı, admin onayı şart`.
Bu zincir sağlam ama **iki delik** kaldı:

**Delik A — ML eğitilmemişse / yanlış eğitilmişse güvenlik ağı yok.** (P0) ✅ **ÇÖZÜLDÜ (2026-06-24)**
İki ayrı bug bulundu ve düzeltildi:
1. **`train_model.py` saniye üretiyordu** (ms beklenirken) → her insan profili `MIN_DELTA_MS`
   ile elenip feature_vector tamamen SIFIR çıkıyor, model 10k özdeş sıfır vektörle eğitiliyordu.
   → ms'e çevrildi; artık ~9965/10000 gerçek insan profili eğitime giriyor.
2. **`layer3_ml.py` anomaly_score normalizasyonu yanlıştı** (`-score_samples*2`). IsolationForest'ın
   score_samples'ı normal noktada da ~-0.45 olduğundan normal insan da anomaly≈0.9 alıp flag yiyordu.
   → `decision_function` tabanlı (sınır=0) normalizasyona geçildi.

**Ölçüm** (`evaluate_model.py`, offline, temporal hariç tek-pencere = FP üst sınırı):
| Profil | FP-flag | FP-confirm (oto-aksiyon) |
|---|---|---|
| İnsan | %2.2 | **%0.0** |
| naive bot | — | %100 confirm |
| advanced bot | — | %93 confirm (%100 flag) |
| very-advanced bot | — | %24 confirm (%94 flag) |
| ultimate-AI bot (AR(1) insan klonu) | — | %3 confirm (%39 flag) |

İnsan oto-aksiyon FP'si **%0**. İstatistiksel insan-klonu botlar kısmen kaçar — bu, davranışsal
tespitin temel ve kabul edilebilir sınırıdır (mükemmel klon insandan ayrılamaz). Yeni model
`python train_model.py`, ölçüm `python evaluate_model.py` ile üretilir/tekrarlanır.

**Delik B — global eşik, kişiye kör.** (Faz 3, asıl FP kaldıracı) ✅ **BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-06-24)**
Yapılanlar:
  1. **Per-player trust** (`vektia/core/baseline.py`): her oyuncu+aksiyon için temiz-pencere
     EMA'sı bir güven skoru üretir; bu skor zamansal kanıt artışını yumuşatan bir **leniency**
     çarpanına dönüşür (`temporal.record(..., leniency)`). Kalıcı temiz oyuncu (yüksek trust)
     FP'ye karşı ekstra korunur; bot/yeni hesap (düşük trust) tam hassasiyette kalır. Sert
     whitelist değil — yeterince sürdürülen gerçek makro yine yakalanır (biraz geç).
  2. **Whitelist enforcement** (eskiden EKSİKTİ): Admin paneli `vektia:whitelisted` set'ine
     ekliyordu ama motor bunu hiç kontrol etmiyordu. Artık pipeline `player_record.status ==
     "whitelisted"` ise anında CLEAN döner ve temporal kanıtı sıfırlar.
  3. **Temporal eşik bug'ı**: `temporal_confirm_threshold=2.5`, HIGH kanıt asimptotuna
     (1.0/(1-0.6)=2.5) EŞİT olduğu için asla aşılamıyordu (sürdürülen makro temporal'da
     hiç CONFIRMED olmuyordu — ölü kod). 1.9'a çekildi (config + .env + .env.example).
  Testler: `tests/test_baseline.py` (5 test) + güncellenen `tests/test_temporal.py` geçiyor.

**Kalan (opsiyonel, daha güçlü):** per-player **baseline-deviation** — oyuncunun kendi geçmiş
feature dağılımına göre z-skor; "bu oyuncu için anormal mi?" (ör. yüksek-cv geçmişi olan biri
aniden ~0 cv'ye düşerse = makro açıldı sinyali). Mevcut trust yumuşatma + ML güvenlik ağı zaten
FP-confirm'i %0'a indirdiği için bu bir sonraki iyileştirme turuna bırakıldı.

**Faz 4 — ölçmeden kalibrasyon yapma.** ◐ **KISMEN YAPILDI (2026-06-24)**
  1. ✅ **Shadow mod:** `VEKTIA_SHADOW_MODE=true` iken pipeline kararı hesaplar ama aksiyon
     ALMAZ; `get_pipeline_stats()` içinde `shadow_would_flag`/`shadow_would_confirm` sayılır.
     Yeni eşikleri canlıda, gerçek oyuncuyu etkilemeden ölçmek için.
  2. ✅ **`false_positive_rate` beslemesi:** `get_dashboard_stats` artık FP oranını
     `metrics.false_positive_rate(flagged, banned, whitelisted)` ile hesaplayıp döndürüyor
     (whitelist = admin "yanlış işaretlendi" geri bildirimi). Dashboard'a otomatik akıyor.
     Saf hesap `vektia/core/metrics.py`'de, `tests/test_metrics.py` ile test edildi.
  3. ⬜ **Müşteri-bazlı override:** rhythm game vs survival farklı; eşikler `config.py` + müşteri
     bazlı override ile ayarlanabilir olsun. (Client tablosuna eşik kolonları/override gerekir.)
  4. ⬜ **Eski-vs-yeni A/B & `ANOMALY_SLOPE` kalibrasyonu:** shadow verisi biriktikçe eşikleri
     ve ML eğimini gerçek FP/flag oranına göre ayarla.

**Düşük riskli ek sertleştirmeler (opsiyonel):**
  - `max_window` 20→40–50: daha büyük örneklem, otokorelasyon/range_ratio daha güvenilir, şans
     eseri FP azalır. (Redis RAM/gecikme etkisini yük testiyle ölç.)
  - Hard `return 1.0` bloklarını (FP-1…FP-5) skorlu sinyale çevir; yalnızca *varyans tam 0 +
     çok pencerede sabit* doğrudan yüksek risk kalsın.

> **Önerilen sıra:** Delik A (ML eğitimi, P0) → Faz 4 ölçüm altyapısı (shadow + FP telemetrisi) →
> Faz 3 (per-player baseline + whitelist) → eşik kalibrasyonu. Ölçüm altyapısı önce gelir ki
> Faz 3 değişikliklerinin FP'yi gerçekten düşürdüğünü kanıtlayabilelim.
