import time
import requests
import random

API_URL = "http://localhost:8000/api/v1/telemetry/event"

def send_player_data(api_key, player_id, profile_type, num_events=25):
    """
    Belirli bir oyuncu için API'ye sahte telemetri verisi gönderir.
    profile_type: 'human', 'perfect_bot', 'jitter_bot', 'sine_bot'
    """
    headers = {"X-Vektia-Key": api_key}
    print(f"\n[{profile_type.upper()}] '{player_id}' profili için veri gönderiliyor (API Key: {api_key[:12]}...)...")
    
    current_time = time.time() * 1000  # Milisaniye cinsinden başlangıç zamanı
    
    for i in range(num_events):
        # 1. Bekleme süresini belirle (Delta)
        if profile_type == 'perfect_bot':
            delta = 100.0
        elif profile_type == 'jitter_bot':
            delta = random.uniform(99.999, 100.001)
        elif profile_type == 'sine_bot':
            import math
            delta = 100.0 + math.sin(i * 0.5) * 5.0
        else:
            delta = random.uniform(80.0, 180.0)
            
        current_time += delta
        
        # 2. Payload oluştur
        payload = {
            "player_id": player_id,
            "action_type": "hit",
            "timestamp": current_time,
            "server_id": "test_server_1"
        }
        
        # 3. API'ye gönder
        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=2)
            if response.status_code == 200:
                data = response.json()
                layer = data.get("layer", 0)
                risk_level = data.get("risk_level", "clean")
                
                if layer > 1 and risk_level != "clean":
                    print(f"  -> [UYARI] {player_id} tespit edildi! Katman: {layer}, Risk: {risk_level}, Skor: {data.get('risk_score')}")
            else:
                print(f"  -> [HATA] {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Bağlantı hatası: {e}")
            return
            
        # İstekler arası sunucuyu yormamak için çok hafif bir bekleme
        time.sleep(0.05)
        
    print(f"[{profile_type.upper()}] '{player_id}' tamamlandı.")


if __name__ == "__main__":
    print("==================================================")
    print(" VEKTIA CANLI API SİMÜLASYONU BAŞLIYOR (MULTI-TENANT)")
    print(" Arayüzü açın: http://localhost:8000/admin/")
    print("==================================================\n")
    
    # Client A: Studio A (Test)
    key_a = "test_api_key_A"
    send_player_data(key_a, "human_player_A", profile_type="human")
    send_player_data(key_a, "pure_macro_bot_A", profile_type="perfect_bot")
    
    # Client B: Studio B (Test)
    key_b = "test_api_key_B"
    send_player_data(key_b, "human_player_B", profile_type="human")
    send_player_data(key_b, "random_jitter_bot_B", profile_type="jitter_bot")
    
    print("\n[+] Tüm veriler gönderildi. Lütfen Admin Dashboard'u kontrol edin!")
