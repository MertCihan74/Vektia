import asyncio
import httpx
import time
import random
import numpy as np

API_URL = "http://localhost:8000/api/v1/telemetry/batch"

# Sadece tek bir hesabı test ediyoruz (PRO hesabı)
CLIENT = {"name": "PRO", "api_key": "test_api_key_A", "tier": "premium"}

# Test senaryoları
NUM_NORMAL = 50
NUM_NAIVE_BOT = 25
NUM_ADVANCED_BOT = 25
NUM_VERY_ADVANCED_BOT = 25
NUM_ULTIMATE_AI_BOT = 25
EVENTS_PER_PLAYER = 25

async def send_batch(client, events):
    headers = {
        "X-Vektia-Key": client['api_key'],
        "Content-Type": "application/json"
    }
    payload = {
        "server_id": "test_server_1",
        "events": events
    }
    
    # Sunucuyu boğmamak için rastgele küçük bir bekleme
    await asyncio.sleep(random.uniform(0.1, 2.0))
    
    async with httpx.AsyncClient() as session:
        try:
            response = await session.post(API_URL, json=payload, headers=headers, timeout=30.0)
            if response.status_code == 429:
                await asyncio.sleep(2)
                return await send_batch(client, events)
            elif response.status_code != 200:
                print(f"Error {response.status_code}: {response.text}")
            return response.status_code
        except Exception as e:
            print(f"Exception for batch: {type(e).__name__} - {e}")
            return str(e)

async def simulate_normal_player(player_id):
    """Gerçek insan: Yüksek sapma (0.150s - 0.600s), anlık duraksamalar"""
    current_time = time.time() * 1000.0
    events = []
    for _ in range(EVENTS_PER_PLAYER):
        if random.random() < 0.10:
            reaction_time_ms = random.uniform(1000.0, 3000.0)
        else:
            reaction_time_ms = np.random.lognormal(mean=5.0, sigma=0.4) # Log-normal in ms (mean~150ms)
            reaction_time_ms = max(120.0, reaction_time_ms)
            
        current_time += reaction_time_ms
        coords = {"x": 500.0 + random.uniform(-2.0, 2.0), "y": 500.0 + random.uniform(-2.0, 2.0), "z": 0.0}
        events.append({"player_id": player_id, "action_type": "click", "value": reaction_time_ms, "timestamp": current_time, "coords": coords})
    await send_batch(CLIENT, events)

async def simulate_naive_bot(player_id):
    """Basit Bot: Mükemmel zamanlama, çok düşük sapma"""
    current_time = time.time() * 1000.0
    events = []
    for _ in range(EVENTS_PER_PLAYER):
        reaction_time_ms = 50.0 + random.uniform(-1.0, 1.0)
        current_time += reaction_time_ms
        coords = {"x": 500.0, "y": 500.0, "z": 0.0} # Bot has 0 jitter
        events.append({"player_id": player_id, "action_type": "click", "value": reaction_time_ms, "timestamp": current_time, "coords": coords})
    await send_batch(CLIENT, events)

async def simulate_advanced_bot(player_id):
    """Gelişmiş Bot: İnsan taklidi yapmaya çalışan, rastgelelik eklenmiş bot"""
    current_time = time.time() * 1000.0
    events = []
    for _ in range(EVENTS_PER_PLAYER):
        reaction_time_ms = 100.0 + random.uniform(-20.0, 20.0)
        current_time += reaction_time_ms
        coords = {"x": 500.0, "y": 500.0, "z": 0.0}
        events.append({"player_id": player_id, "action_type": "click", "value": reaction_time_ms, "timestamp": current_time, "coords": coords})
    await send_batch(CLIENT, events)

async def simulate_very_advanced_bot(player_id):
    """Çok Gelişmiş Bot: Log-Normal dağılımlı, insan taklidi"""
    current_time = time.time() * 1000.0
    events = []
    deltas_ms = np.random.lognormal(mean=np.log(120.0), sigma=0.2, size=EVENTS_PER_PLAYER)
    if random.random() < 0.3:
        deltas_ms[random.randint(0, EVENTS_PER_PLAYER-1)] += random.uniform(1000.0, 3000.0)
    deltas_ms = np.clip(deltas_ms, 50.0, 5000.0)
    
    for reaction_time_ms in deltas_ms:
        current_time += float(reaction_time_ms)
        coords = {"x": 500.0, "y": 500.0, "z": 0.0}
        events.append({"player_id": player_id, "action_type": "click", "value": float(reaction_time_ms), "timestamp": current_time, "coords": coords})
    await send_batch(CLIENT, events)

async def simulate_ultimate_ai_bot(player_id):
    """Ultimate AI Bot: Olabilecek en gelişmiş makro (Tam bir insan klonu)"""
    current_time = time.time() * 1000.0
    events = []
    
    # İnsanın mükemmel istatistiklerini taklit et
    # AR(1) süreci ile otokorelasyon oluştur (örn: rho = 0.3)
    rho = 0.3
    mu = np.log(250.0)
    sigma = 0.4
    
    deltas_ms = []
    prev_val = np.random.normal(mu, sigma)
    
    for _ in range(EVENTS_PER_PLAYER):
        # AR(1) denklemi
        noise = np.random.normal(0, sigma * np.sqrt(1 - rho**2))
        val = mu + rho * (prev_val - mu) + noise
        prev_val = val
        deltas_ms.append(np.exp(val))
        
    deltas_ms = np.array(deltas_ms)
    # Medyan ve Ortalama heuristiclerine takılmamak için insan sınırlarında (min 151ms) tut
    deltas_ms = np.clip(deltas_ms, 155.0, 5000.0)
    
    for reaction_time_ms in deltas_ms:
        current_time += float(reaction_time_ms)
        coords = {"x": 500.0, "y": 500.0, "z": 0.0} # Even the ultimate AI bot often forgets to jitter the mouse
        events.append({"player_id": player_id, "action_type": "click", "value": float(reaction_time_ms), "timestamp": current_time, "coords": coords})
    await send_batch(CLIENT, events)

async def main():
    print(f"[{CLIENT['name']}] hesabı için 150 oyunculuk test başlatılıyor...")
    print(f" - {NUM_NORMAL} Normal Oyuncu")
    print(f" - {NUM_NAIVE_BOT} Basit Bot")
    print(f" - {NUM_ADVANCED_BOT} Gelişmiş Bot")
    print(f" - {NUM_VERY_ADVANCED_BOT} Çok Gelişmiş Bot")
    print(f" - {NUM_ULTIMATE_AI_BOT} Ultimate AI Bot")
    
    tasks = []
    sem = asyncio.Semaphore(10)
    
    async def run_with_sem(coro):
        async with sem:
            await coro

    # 1. Normal oyuncular
    for i in range(NUM_NORMAL):
        player_id = f"test_human_{i}"
        tasks.append(run_with_sem(simulate_normal_player(player_id)))
        
    # 2. Basit Botlar
    for i in range(NUM_NAIVE_BOT):
        player_id = f"test_bot_naive_{i}"
        tasks.append(run_with_sem(simulate_naive_bot(player_id)))
        
    # 3. Gelişmiş Botlar
    for i in range(NUM_ADVANCED_BOT):
        player_id = f"test_bot_advanced_{i}"
        tasks.append(run_with_sem(simulate_advanced_bot(player_id)))
        
    # 4. Çok Gelişmiş Botlar
    for i in range(NUM_VERY_ADVANCED_BOT):
        player_id = f"test_bot_very_advanced_{i}"
        tasks.append(run_with_sem(simulate_very_advanced_bot(player_id)))
        
    # 5. Ultimate AI Botlar
    for i in range(NUM_ULTIMATE_AI_BOT):
        player_id = f"test_bot_ultimate_{i}"
        tasks.append(run_with_sem(simulate_ultimate_ai_bot(player_id)))
        
    await asyncio.gather(*tasks)
    print("Tum mock data basariyla gonderildi!")

if __name__ == "__main__":
    asyncio.run(main())
