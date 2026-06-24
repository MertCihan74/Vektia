# CLAUDE.md — Vektia Çalışma Rehberi

> Bu dosya, gelecekteki oturumların projeyi yeniden tarayıp token harcamaması için
> yazıldı. **Önce burayı oku.** Kaynak dosyaları yalnızca burada işaret edilen ilgili
> bölümü değiştireceksen aç. Bir şey değiştirince bu dosyayı güncel tut.

## Proje bir cümlede
Vektia = **platform-bağımsız, ML destekli, davranışsal anti-cheat SaaS**. İstemciye
güvenmez; yalnızca sunucudan gelen telemetriye (zaman damgası + koordinat + aksiyon tipi)
bakıp istatistik + Isolation Forest ile makro/bot/auto-clicker ayıklar.

## Şu anki ana iş: Yanlış Pozitif (False Positive) Azaltma
**Hedef:** Gerçek oyuncunun (özellikle ritmik/yetenekli sol-tık yapan oyuncunun) yanlışlıkla
bot işaretlenmesini minimuma indirmek. **Felsefe: precision > recall** — bir botu kaçırmak,
bir gerçek oyuncuyu banlamaktan iyidir. Detaylı yol haritası: `FALSE_POSITIVE_REDUCTION_PLAN.md`.

## Mimari akış (telemetri → karar)
```
Event → L1 Sliding Window (Redis) → L2 İstatistik → L2.5 Temporal Kanıt → (şüpheliyse) ML kuyruğu → L3 ML Worker
```
- **L1** `vektia/core/layer1_redis.py` — oyuncu başına son `max_window`(=20) eylemi Redis'te tutar (Lua sliding window; yoksa fallback). `timestamp|x|y` formatı.
- **L2** `vektia/core/layer2_stats.py` — pencereden delta'ları çıkarır, metrik üretir (std, cv, entropy, autocorrelation, skewness, range_ratio), `_evaluate_risk` ile pencere riski (CLEAN/LOW/SUSPICIOUS/HIGH) verir.
- **L2.5** `vektia/core/temporal.py` — **FP ilacının kalbi.** Pencere riskini söndürmeli (decay) bir kanıt skorunda biriktirir. **Tek pencere ASLA CONFIRMED üretmez**; ~3 ardışık HIGH gerekir. Redis'te `...:suspicion` anahtarı. `record(..., leniency)` ile baseline güvenine bağlı.
- **L2.6 (Faz 3)** `vektia/core/baseline.py` — per-player **trust** (temiz-pencere EMA'sı). Güvenilen oyuncunun şüpheli pencereleri kanıta daha az katkı yapar (leniency). Redis'te `...:baseline` hash'i.
- **Pipeline** `vektia/core/pipeline.py` — yukarıdakileri sırayla çağırır. **Whitelist enforcement**: `player_record.status == "whitelisted"` ise anında CLEAN + temporal reset. Kanıt yetersizse CLEAN, yeterliyse flag + ML kuyruğu + alert.
- **L3** `vektia/core/layer3_ml.py` + `vektia/worker/ml_worker.py` — Isolation Forest. **Güvenlik ağı:** ML her şüpheli için çalışır; model "normal" derse heuristik 1.0 olsa bile CONFIRMED vermez.

## Kritik gotcha'lar (bunları bilmezsen hata yaparsın)
1. **Birim = MİLİSANİYE.** Tüm zaman eşikleri ms (`mean_delta < 35.0` = 35ms). `TELEMETRY_DATA_FORMAT.md` ve `models.py` ms tanımlar. Eskiden saniye varsayan eşikler vardı; taşındı. Yeni eşik eklerken ms kullan.
2. **ML güvenlik ağı yalnızca model EĞİTİLMİŞSE çalışır.** `layer3_ml.py:predict()` model eğitilmemişse L2 skorunu aynen döndürür → HIGH, HIGH kalır → CONFIRMED'e gidebilir. Model `models/*.joblib` **gitignore'da** — her ortam `python train_model.py` ile kendi modelini üretir (deploy'da sklearn 1.7.0). Offline FP/FN ölçümü: `python evaluate_model.py` (sunucu gerektirmez). **DÜZELTİLDİ (2026-06-24):** (a) `train_model.py` saniye üretiyordu → ms'e çevrildi (eskiden tüm feature'lar sıfır çıkıp model çöp eğitiliyordu); (b) `layer3_ml.py` anomaly_score `-score_samples*2` ile yanlış normalize ediyordu → `decision_function` tabanlı normalizasyona geçildi (eskiden normal insan da anomaly≈0.9 alıp flag yiyordu). Sonuç: insan FP-confirm %0, bot recall yüksek.
3. **Tüm FP işi commit edilmemiş** (working tree). Sadece 3 commit var. Önemli mantık `git diff`'te yaşıyor.
4. **Sliding pencere üst üste biner** — her yeni tıklama son 20'yi yeniden analiz eder. Bu yüzden tek bir düzensiz insan tıklaması kanıt zincirini kırar; FP korumasının doğal kaynağı budur.
5. Hard kurallar (`return 1.0, RiskLevel.HIGH`) hâlâ L2'de var ama **artık tek başına ban yapmaz** — temporal katmanı süzer. Bunları kaldırma; temporal'a güven.
6. **`temporal_confirm_threshold` < 2.5 OLMALI.** HIGH kanıt asimptotu `high_inc/(1-decay)=1.0/0.4=2.5`. Eşik 2.5'e EŞİTSE asla aşılmaz → temporal CONFIRMED ölü kod. Varsayılan 1.9'a çekildi (config + .env + .env.example). `.env` config default'unu EZER — ayar değişikliğinde .env'i de güncelle.
7. **Whitelist artık motorda zorlanıyor.** Admin paneli `vektia:whitelisted` set'ine ekliyordu ama pipeline bakmıyordu; şimdi `player_record.status=="whitelisted"` → CLEAN + temporal reset.
8. **Shadow mod (Faz 4):** `VEKTIA_SHADOW_MODE=true` iken pipeline kararı hesaplar ama AKSİYON ALMAZ (flag/ML/ban yok); `get_pipeline_stats()` içindeki `shadow_would_flag`/`shadow_would_confirm` sayaçlarını işler. Yeni eşikleri canlıda güvenle ölçmek için. Saf metrik hesapları `vektia/core/metrics.py` (sqlalchemy/redis'siz, test edilir).

## Eşiklerin yaşadığı yer
- İstatistik eşikleri: `layer2_stats.py:_evaluate_risk` (range_ratio<1.03, mean_delta<35, mean_delta<60&cv<0.10, autocorrelation>0.80, spatial std_x==std_y==0).
- Config eşikleri: `vektia/config.py` → `bot_threshold`(3.0ms), `suspicious_threshold`(15.0ms), `max_window`(20) ve **tüm `temporal_*`** (decay=0.6, high_increment=1.0, suspect=0.8, confirm=2.5, ttl=120s).
- Hepsi `VEKTIA_*` env değişkeniyle override edilebilir.

## Veri modeli (`vektia/core/models.py`)
`ActionType`(hit/click/move/trade/interact/cast) · `RiskLevel`(clean/low/suspicious/high/confirmed) · `BanStatus`(active/flagged/banned/**whitelisted**) · `StatsResult.feature_vector` = ML'in 8 boyutu. `DashboardStats.false_positive_rate` artık **besleniyor** (Faz 4): `get_dashboard_stats` → `metrics.false_positive_rate(flagged, banned, whitelisted)` = whitelist (admin "yanlış işaretlendi") / aksiyon alınanlar.

## Çalıştırma / test
- Çalıştırma: `docker-compose up -d --build` (Redis+PG+API+ML worker). Python 3.11+, Redis 7+, PG 15+.
- Testler: `tests/test_temporal.py` (FP güvencesi — tek pencere asla confirmed), `tests/test_layer2.py`, `tests/test_layer3_ml.py`. Çalıştır: `pytest tests/ -q`.
- Hızlı sözdizim kontrolü (bağımlılık gerektirmez): modülleri `ast.parse` ile derle.

## Dosya haritası (yalnız gerekeni aç)
- Çekirdek motor: `vektia/core/` (yukarıda).
- API: `vektia/api/` (websocket.py canlı akış), DB: `vektia/db/` (database.py, repositories.py, redis_client.py).
- Panel: `admin/*.html` (B2B müşteri+admin), `public/demo.html` (canlı makro-avı simülasyonu).
- ML scriptleri (untracked): `train_model.py`, `generate_mock_data.py`, `run_ml_experiment.py`.
- Dokümanlar: `README.md`, `details.md`, `TELEMETRY_DATA_FORMAT.md`, `FALSE_POSITIVE_REDUCTION_PLAN.md`.

## Çalışma tarzı
- Kullanıcı **Türkçe** iletişim kuruyor; Türkçe yanıtla.
- Repo dokümanları Türkçe + İngilizce teknik terim karışımı; aynı stili koru.
