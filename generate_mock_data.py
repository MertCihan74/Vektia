import asyncio
import httpx
import time
import random
import math

API_URL = "http://localhost:8000/api/v1/telemetry/event"

CLIENTS = [
    {"name": "PRO", "api_key": "test_api_key_A", "tier": "premium"},
    {"name": "FREE", "api_key": "vkt_free_123", "tier": "free"},
    {"name": "PAYG", "api_key": "test_api_key_payg", "tier": "payg"},
    {"name": "ENTERPRISE", "api_key": "test_api_key_enterprise", "tier": "enterprise"},
]

async def send_event(client, player_id, event_type, value, custom_timestamp):
    headers = {
        "X-Vektia-Key": client['api_key'],
        "Content-Type": "application/json"
    }
    payload = {
        "player_id": player_id,
        "action_type": event_type,
        "value": value,
        "timestamp": custom_timestamp
    }
    async with httpx.AsyncClient() as session:
        try:
            response = await session.post(API_URL, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"Error {response.status_code} from {client['name']}: {response.text}")
            return response.status_code
        except Exception as e:
            print(f"Exception from {client['name']}: {str(e)}")
            return str(e)

async def simulate_normal_player(client, player_id, num_events=25):
    print(f"[{client['name']}] Normal Player {player_id} basliyor...")
    current_time = time.time()
    for _ in range(num_events):
        reaction_time = random.uniform(0.200, 0.500)
        current_time += reaction_time
        await send_event(client, player_id, "click", reaction_time, current_time)
        await asyncio.sleep(0.01)
    print(f"[{client['name']}] Normal Player {player_id} bitti.")

async def simulate_bot_player(client, player_id, num_events=25):
    print(f"[{client['name']}] Bot Player {player_id} basliyor...")
    current_time = time.time()
    for _ in range(num_events):
        reaction_time = 0.050 + random.uniform(-0.001, 0.001)
        current_time += reaction_time
        await send_event(client, player_id, "click", reaction_time, current_time)
        await asyncio.sleep(0.01)
    print(f"[{client['name']}] Bot Player {player_id} bitti.")

async def main():
    tasks = []
    for client in CLIENTS:
        for i in range(2):
            player_id = f"user_{client['name'].lower()}_normal_{i}"
            tasks.append(simulate_normal_player(client, player_id))
        
        bot_id = f"user_{client['name'].lower()}_bot_1"
        tasks.append(simulate_bot_player(client, bot_id, num_events=25))
        
    await asyncio.gather(*tasks)
    print("Tum mock data basariyla gonderildi!")

if __name__ == "__main__":
    asyncio.run(main())
