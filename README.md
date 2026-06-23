# Vektia — B2B ML-Based Behavioral Anti-Cheat SaaS

<p align="center">
  <strong>🛡️ Yapay Zeka (ML) Destekli Davranışsal Hile Tespiti</strong><br>
  Platform bağımsız (Platform-Agnostic) B2B SaaS altyapısıyla oyuncu davranışlarını telemetri verisi üzerinden analiz eder.<br>
  Herhangi bir oyun motorunda (FiveM, Unity, Unreal, Web) çalışabilir.
</p>

---

## 🌟 Neden Vektia?
Geleneksel anti-cheat sistemleri istemci (client) tarafında çalışır ve bypass edilebilir. **Vektia**, istemciye güvenmez. Sadece sunucu taraflı gönderilen zaman, koordinat ve aksiyon verilerine bakarak imkansız reaksiyon hızlarını, bot davranışlarını ve anormallikleri **İstatistik + Makine Öğrenimi (Isolation Forest)** ile tespit eder.

- **Platform Bağımsız:** Sadece HTTP POST istekleri kabul eder.
- **B2B SaaS Altyapısı:** Müşterileriniz kendi üyeliklerini açar, API Key alır ve kotalı/limitsiz planlara (Lemon Squeezy üzerinden) abone olabilirler.
- **Otomatik Engelleme (Auto-Ban):** Müşteriler, risk seviyesine göre (Şüpheli, Yüksek Riskli, Kesin Bot) hesaplara otomatik ban atılmasını veya sadece işaretlenmesini seçebilir.

---

## 🏗️ Mimari & Teknoloji Yığını

```
[Oyun Sunucusu (Lua/C#/Python)] → [REST/HTTP] → [FastAPI] → [PostgreSQL & Redis]
                                                                    ↓
[Admin & Müşteri Paneli (HTML/JS)] ← [Auto-Ban & Webhook Worker] ← [ML Worker (Isolation Forest)]
```

### 3 Katmanlı Filtreleme:
1. **Redis Lua Sliding Window:** Saniyede binlerce veriyi RAM üzerinde tutar.
2. **Matematiksel Filtre (NumPy):** Standart Sapma, Entropi, CV, Otokorelasyon hesaplayıp normal oyuncuları %95 oranında eler.
3. **ML Anomali Tespiti (Isolation Forest):** Kalan şüpheli %5'lik kısmı arka plandaki ML Worker işler ve kesin botları ayırır.

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Python 3.11+
- Redis 7+
- PostgreSQL 15+
- Docker & Docker Compose (Önerilen)

### Docker ile Kurulum (Önerilen)

```bash
# .env dosyasını oluştur
cp .env.example .env

# Tüm mimariyi (Redis, DB, API, ML Worker) ayağa kaldır
docker-compose up -d --build
```

## 📊 Yönetim ve Müşteri Paneli

Vektia, modern ve mobil uyumlu, B2B SaaS modeline uygun bir panele sahiptir.
`http://localhost:8000/admin/` üzerinden giriş yapılabilir.

- **Admin Girişi:** `admin` / `admin123`
- Müşteriler (Oyun Stüdyoları) buradan kendi API Key'lerini alıp abonelik durumlarını görüntüleyebilir, oyuncularının tespit loglarını inceleyebilir ve **Otomatik Engelleme** ayarlarını yönetebilir.

## 🎮 Platform Bağımsız SDK'lar

Her dil ve motorla uyumludur. Hazır SDK'lar `sdk/` klasörü altındadır.

### FiveM (Lua)
`sdk/lua/vektia_telemetry.lua` resource'unu sunucuya ekleyin. Native `weaponDamageEvent` ve hareket verilerini otomatik izler.

### Unity / C# / .NET
```csharp
var client = new VektiaTelemetry("http://localhost:8000", "your-api-key");
await client.TrackAsync("player_123", "hit", x: 100, y: 200, z: 10);
```

### Python
```python
from sdk.python.vektia_client import VektiaClient
client = VektiaClient("http://localhost:8000", "your-api-key")
await client.track("player_123", "hit")
```

### HTTP (Curl)
```bash
curl -X POST http://localhost:8000/api/v1/telemetry/event \
  -H "X-Vektia-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"player_id":"123","action_type":"hit","timestamp":1719129600000}'
```

## 🧪 Testler

```bash
# Simülasyonu çalıştır (Sistemi test eden sahte trafik üretir)
docker-compose exec api python scripts/simulate.py

# Otomatik Ban (Auto-Ban) senaryosunu test et
docker-compose exec api python vektia/test_autoban.py
```

## 📜 Lisans

Proprietary — Tüm hakları saklıdır.
