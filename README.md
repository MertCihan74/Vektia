# Vektia — Event-Driven Behavioral Anti-Cheat API

<p align="center">
  <strong>🛡️ Davranışsal Hile Tespit Sistemi</strong><br>
  Sunucu taraflı telemetri ile oyuncu davranışlarını analiz eder.<br>
  İstemciye müdahale etmez, kişisel veri toplamaz, sadece davranışı inceler.
</p>

---

## 🏗️ Mimari

```
[Oyun Sunucusu] → [WebSocket/HTTP] → [Redis Sliding Window] → [İstatistiksel Analiz] → [ML Anomali Tespiti] → [Admin Paneli]
```

**Katmanlı Elek:** Milyonlarca oyuncudan gelen veriyi 3 katmanda eleyerek sunucu yükünü minimumda tutar.

| Katman | Teknoloji | Görev | Eleme |
|--------|-----------|-------|-------|
| 1 | Redis Lua | Sliding Window — son 20 eylemi tut | Veri toplama |
| 2 | NumPy | Standart Sapma + Entropi + CV + Otokorelasyon | %95 temiz oyuncuyu eler |
| 3 | Isolation Forest | ML anomali tespiti | Kalan %1'i kesin tespit |

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Python 3.11+
- Redis 7+
- Docker & Docker Compose (opsiyonel)

### Yerel Kurulum

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. .env dosyasını düzenle
cp .env.example .env

# 3. Redis başlat (Docker ile)
docker run -d --name vektia-redis -p 6379:6379 redis:7-alpine

# 4. Sunucuyu başlat
uvicorn vektia.main:app --reload --host 0.0.0.0 --port 8000

# 5. Simülasyon çalıştır
python scripts/simulate.py
```

### Docker Compose

```bash
docker-compose up -d
```

## 📊 Admin Paneli

`http://localhost:8000/admin/` adresinden erişin.

- **Varsayılan Kullanıcı:** `admin`
- **Varsayılan Şifre:** `admin123`

## 📡 API Dokümantasyonu

- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

### Telemetri Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/telemetry/event \
  -H "X-Vektia-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "player_123",
    "action_type": "hit",
    "timestamp": 1719129600000,
    "coords": {"x": 100.5, "y": 200.3, "z": 10.0}
  }'
```

## 🎮 Oyun Entegrasyonu

### FiveM (Lua)
`sdk/lua/vektia_telemetry.lua` dosyasını sunucunuzun resources klasörüne kopyalayın.

### Python
```python
from sdk.python.vektia_client import VektiaClient

client = VektiaClient("http://localhost:8000", "your-api-key")
await client.connect()
await client.track("player_123", "hit")
```

### C# / Unity
```csharp
var client = new VektiaTelemetry("http://localhost:8000", "your-api-key");
client.Track("player_123", "hit", x: 100, y: 200, z: 10);
```

## 🧪 Testler

```bash
# Tüm testleri çalıştır
pytest tests/ -v

# Simülasyon
python scripts/simulate.py
```

## 📜 Lisans

Proprietary — Tüm hakları saklıdır.
