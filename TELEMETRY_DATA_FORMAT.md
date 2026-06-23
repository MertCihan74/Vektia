# Vektia Telemetry Data Requirements

Vektia'nın Makine Öğrenimi (ML) tabanlı anti-cheat modelinin doğru çalışabilmesi için müşteri (oyun stüdyosu) sunucularından belirli bir standartta JSON verisi alması gerekir. 

Vektia, istemciden (client) ekran görüntüsü, dosya taraması veya bellek (RAM) okuması gibi **istilacı (invasive) veriler talep etmez**. Sistem tamamen zamanlama ve ritim analizi üzerine kuruludur.

Aşağıda Vektia API'sine `/api/v1/telemetry/event` (veya `/batch`) endpointi üzerinden gönderilmesi gereken veri yapısı ve açıklamaları yer almaktadır.

---

## 📦 Örnek JSON Payload

```json
{
  "player_id": "steam:1100001xxxxxxxx",
  "action_type": "hit",
  "timestamp": 1719129600550,
  "server_id": "tr_survival_01",
  "coords": {
    "x": 105.2,
    "y": 204.1,
    "z": 10.0
  },
  "metadata": {
    "weapon_id": "weapon_assaultrifle"
  }
}
```

---

## 🔴 Zorunlu Alanlar (Mandatory Fields)

Bu alanların gönderilmemesi durumunda API veriyi reddeder (HTTP 422 Unprocessable Entity) veya arka plandaki ML algoritması ritim hesaplayamaz.

| Alan Adı | Veri Tipi | Açıklama |
| :--- | :--- | :--- |
| `player_id` | `String` | Oyuncuyu temsil eden benzersiz kimlik (Steam Hex, DB ID, vb.). ML modeli her bir oyuncuyu bu ID'ye göre bellekte bağımsız olarak izler ve profiller. |
| `action_type` | `String` | Oyuncunun yaptığı eylemin kategorisi. Sistem temel ritimleri eylem bazında ayırır. |
| `timestamp` | `Integer` | Olayın gerçekleştiği milisaniye cinsinden tam zaman (Unix Epoch Time in ms veya oyun motorunun kendi Timer'ı `GetGameTimer()`). **ML modelinin can damarıdır.** |

### Kabul Edilen Temel `action_type` Değerleri:
* **`hit` / `shoot`:** Silah ateşleme, yumruk atma, yetenek kullanma (Combat eylemleri). Auto-clicker ve makro tespitleri için en kritik eylemdir.
* **`move` / `walk`:** Hareket başlangıcı/bitişi veya periyodik lokasyon güncellemeleri. Aynı rotada, aynı ms aralıklarıyla saatlerce yürüyen farm botlarını tespit eder.
* **`interact` / `farm` / `trade`:** NPC ile konuşma, eşya toplama, arayüz butonlarına tıklama.

---

## 🟡 Opsiyonel Alanlar (Optional Fields)

Bu verilerin gönderilmesi zorunlu değildir ancak sistemin doğruluğunu artırır ve gelişmiş analizler (Hız hilesi, Işınlanma) yapılmasına olanak tanır.

| Alan Adı | Veri Tipi | Açıklama |
| :--- | :--- | :--- |
| `server_id` | `String` | Müşterinin birden fazla oyun sunucusu / haritası / kanalı varsa bunları ayırt etmek için kullanılır. |
| `coords` | `Object` | Eylem sırasındaki 3 boyutlu konum (Örn: `{"x": 10.5, "y": 20.0, "z": 0.0}`). İki `timestamp` arasında imkansız mesafeler kat eden oyuncuların (SpeedHack/Teleport) tespiti için kullanılır. |
| `metadata` | `Object` | Müşterinin dilediği özel verileri ekleyebileceği serbest alandır (Örn: Hangi silah kullanıldı, vurulan hedefin ID'si vb.). |

---

## ⚙️ Entegrasyon Tavsiyeleri

1. **Toplu Gönderim (Batching):** Performans optimizasyonu için verileri tek tek atmak yerine `BATCH` endpointini (`/api/v1/telemetry/batch`) kullanarak 10-50 olayı biriktirip tek bir HTTP POST ile göndermeniz tavsiye edilir (Bakınız: `sdk/lua/vektia_telemetry.lua`).
2. **Hassas Zamanlama:** `timestamp` bilgisinin sunucu (Server) zamanına göre değil, eğer güvenli kabul ediliyorsa eylemin oyunda tetiklendiği ilk ana en yakın milisaniyeyi baz alması modelin tespit oranını yükseltir.
3. **Non-Blocking İletişim:** HTTP isteklerinin oyun sunucusunun ana thread'ini (Main Thread) bloklamaması için Asenkron/Non-blocking metotlar kullanılmalıdır.
