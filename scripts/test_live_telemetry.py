import requests
import random
import time
import json
from datetime import datetime, timezone

BASE_URL = "http://localhost:8000"

def generate_telemetry_batch(player_id: str, is_bot: bool, count: int = 50):
    events = []
    t = time.time() * 1000
    for _ in range(count):
        # Bot: Aşırı sabit tıklama (Jitter çok düşük, std < 0.005)
        if is_bot:
            t += 100.0 + random.uniform(-0.001, 0.001)
        else:
            # İnsan: Doğal dalgalanma
            t += random.uniform(50.0, 200.0)
            
        events.append({
            "player_id": player_id,
            "action_type": "click",
            "timestamp": t,
            "coords": {"x": random.uniform(0, 1920), "y": random.uniform(0, 1080), "z": 0.0}
        })
    
    return {
        "events": events,
        "server_id": "test_server_1"
    }

def send_telemetry(api_key: str, payload: dict):
    headers = {"X-Vektia-Key": api_key, "Content-Type": "application/json"}
    try:
        res = requests.post(f"{BASE_URL}/api/v1/telemetry/batch", json=payload, headers=headers)
        return res.status_code, res.json()
    except Exception as e:
        return 500, str(e)

def main():
    print("🚀 Vektia Canlı API Testi Başlıyor...")
    
    # İki Müşteri İçin API Anahtarları (Bunu docker psql ile eklemiştik)
    FREE_API_KEY = "vkt_free_123"
    PREMIUM_API_KEY = "vkt_premium_123"
    
    # 1. FREE Müşteri İçin Test
    print(f"\n[FREE STUDIO] ({FREE_API_KEY}) verileri gönderiliyor...")
    # Normal insan oyuncu gönder
    free_human_data = generate_telemetry_batch("Player_Free_Human_99", is_bot=False, count=60)
    status, resp = send_telemetry(FREE_API_KEY, free_human_data)
    print(f"  -> İnsan Oyuncu Gönderimi: HTTP {status} | {resp}")
    
    # Bot oyuncu gönder
    free_bot_data = generate_telemetry_batch("Player_Free_Hacker_007", is_bot=True, count=60)
    status, resp = send_telemetry(FREE_API_KEY, free_bot_data)
    print(f"  -> Hileci Oyuncu Gönderimi: HTTP {status} | {resp}")
    
    # 2. PREMIUM Müşteri İçin Test
    print(f"\n[PREMIUM STUDIO] ({PREMIUM_API_KEY}) verileri gönderiliyor...")
    # Normal insan oyuncu gönder
    prem_human_data = generate_telemetry_batch("Player_Prem_Human_88", is_bot=False, count=60)
    status, resp = send_telemetry(PREMIUM_API_KEY, prem_human_data)
    print(f"  -> İnsan Oyuncu Gönderimi: HTTP {status} | {resp}")
    
    # Bot oyuncu gönder
    prem_bot_data = generate_telemetry_batch("Player_Prem_MacroBot_999", is_bot=True, count=60)
    status, resp = send_telemetry(PREMIUM_API_KEY, prem_bot_data)
    print(f"  -> Hileci Oyuncu Gönderimi: HTTP {status} | {resp}")

    print("\n✅ Veriler kuyruğa eklendi. ML Worker'ın (arka planda) analiz etmesi için 5 saniye bekleniyor...")
    time.sleep(5)
    
    print("\n🔍 Analiz sonuçlarını görmek için müşteri panellerine giriş yapabilirsiniz:")
    print("   Free Studio E-posta   : free@simulate.com")
    print("   Free Studio API Key   : vkt_free_123")
    print("   --")
    print("   Premium Studio E-posta: premium@simulate.com")
    print("   Premium Studio API Key: vkt_premium_123")

if __name__ == "__main__":
    main()
