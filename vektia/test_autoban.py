import asyncio
import os
import sys
import time
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vektia.db.database import get_session, Client, PlayerRecord
from sqlalchemy import select

API_URL = "http://localhost:8000/api/v1/telemetry/event"

async def send_player_data(api_key, player_id, profile_type, num_events=25):
    headers = {"X-Vektia-Key": api_key}
    print(f"[{profile_type.upper()}] '{player_id}' için veri gönderiliyor...")
    current_time = time.time() * 1000
    
    async with httpx.AsyncClient() as client:
        for i in range(num_events):
            delta = 100.0 if profile_type == 'perfect_bot' else 150.0
            current_time += delta
            payload = {
                "player_id": player_id,
                "action_type": "hit",
                "timestamp": current_time,
                "server_id": "test_server_1"
            }
            try:
                await client.post(API_URL, json=payload, headers=headers, timeout=2)
            except Exception as e:
                pass
            await asyncio.sleep(0.01)

async def setup_clients():
    async with get_session() as session:
        # Client 1: Auto-Ban AÇIK
        result = await session.execute(select(Client).where(Client.email == "autoban_on@test.com"))
        client1 = result.scalar_one_or_none()
        if not client1:
            client1 = Client(name="AutoBan On Studio", email="autoban_on@test.com", api_key="test_key_on", tier="premium", is_active=True, billing_day=1)
            session.add(client1)
            await session.commit()
            await session.refresh(client1)
            
        client1.auto_ban_enabled = True
        client1.auto_ban_high_risk = True
        client1.auto_ban_suspicious = True
        
        # Client 2: Auto-Ban KAPALI
        result = await session.execute(select(Client).where(Client.email == "autoban_off@test.com"))
        client2 = result.scalar_one_or_none()
        if not client2:
            client2 = Client(name="AutoBan Off Studio", email="autoban_off@test.com", api_key="test_key_off", tier="premium", is_active=True, billing_day=1)
            session.add(client2)
            await session.commit()
            await session.refresh(client2)
            
        client2.auto_ban_enabled = False
        client2.auto_ban_high_risk = False
        client2.auto_ban_suspicious = False
        
        await session.commit()
        return client1, client2

async def check_player_status(client_id, player_id):
    async with get_session() as session:
        result = await session.execute(
            select(PlayerRecord).where((PlayerRecord.client_id == client_id) & (PlayerRecord.player_id == player_id))
        )
        return result.scalar_one_or_none()

async def main():
    print("Test veritabanı müşterileri hazırlanıyor...")
    from vektia.db.database import init_database
    await init_database()
    client1, client2 = await setup_clients()
    print(f"Client 1 (Auto-Ban AÇIK): ID={client1.id}, API_KEY={client1.api_key}")
    print(f"Client 2 (Auto-Ban KAPALI): ID={client2.id}, API_KEY={client2.api_key}")
    
    player1 = f"bot_player_autoban_{int(time.time())}"
    player2 = f"bot_player_noautoban_{int(time.time())}"
    
    print("\n--- Telemetri Verileri Gönderiliyor ---")
    await asyncio.gather(
        send_player_data(client1.api_key, player1, "perfect_bot", 30),
        send_player_data(client2.api_key, player2, "perfect_bot", 30)
    )
    
    print("\nArka plan yapay zeka işlemlerinin bitmesi bekleniyor (15 saniye)...")
    await asyncio.sleep(15)
    
    print("\n--- Sonuçlar Kontrol Ediliyor ---")
    p1 = await check_player_status(client1.id, player1)
    p2 = await check_player_status(client2.id, player2)
    
    print(f"Player 1 (Auto-Ban AÇIK): {p1.status if p1 else 'Bulunamadı'} - Sebep: {p1.ban_reason if p1 else ''}")
    print(f"Player 2 (Auto-Ban KAPALI): {p2.status if p2 else 'Bulunamadı'} - Sebep: {p2.ban_reason if p2 else ''}")

if __name__ == "__main__":
    asyncio.run(main())
