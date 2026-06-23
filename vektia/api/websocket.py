"""
Vektia WebSocket Handler

Gerçek zamanlı telemetri akışı (oyun sunucusu → Vektia) ve
canlı admin bildirimleri (Vektia → admin paneli) için WebSocket handler'ları.
"""

import json
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vektia.core.models import TelemetryEvent, ActionType
from vektia.core.pipeline import process_event
from vektia.db.redis_client import get_redis
from vektia.utils.security import validate_api_key, decode_jwt_token
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket"])

# Bağlı admin WebSocket istemcileri
_admin_connections: set[WebSocket] = set()


@router.websocket("/api/v1/telemetry/stream")
async def telemetry_stream(websocket: WebSocket):
    """
    Gerçek zamanlı telemetri akışı.
    
    Oyun sunucusu bu WebSocket üzerinden sürekli telemetri olayları gönderir.
    Bağlantı başında API key doğrulaması yapılır.
    
    Protokol:
    1. İstemci bağlanır
    2. İlk mesaj olarak {"auth": "API_KEY"} gönderir
    3. Sunucu "authenticated" yanıtı verir
    4. İstemci telemetri olaylarını JSON olarak göndermeye başlar
    5. Sunucu her olay için analiz sonucunu döndürür
    """
    await websocket.accept()

    # === Auth Aşaması ===
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        api_key = auth_msg.get("auth", "")

        if not validate_api_key(api_key):
            await websocket.send_json({"error": "Geçersiz API key"})
            await websocket.close(code=4001)
            return

        server_id = auth_msg.get("server_id", "unknown")
        await websocket.send_json({"status": "authenticated", "server_id": server_id})
        logger.info(f"WebSocket telemetri bağlantısı: {server_id}")

    except asyncio.TimeoutError:
        await websocket.send_json({"error": "Auth timeout"})
        await websocket.close(code=4002)
        return

    # === Veri Akışı ===
    try:
        while True:
            raw_data = await websocket.receive_json()

            try:
                event = TelemetryEvent(**raw_data)
                if event.server_id is None:
                    event.server_id = server_id

                result = await process_event(event)

                # Sadece şüpheli sonuçları geri gönder (bant genişliği koruma)
                if result.flagged:
                    await websocket.send_json({
                        "type": "alert",
                        "player_id": result.player_id,
                        "risk_level": result.risk_level.value,
                        "risk_score": result.risk_score,
                    })

            except Exception as e:
                await websocket.send_json({"error": f"İşleme hatası: {str(e)}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket telemetri bağlantısı kapandı: {server_id}")


@router.websocket("/api/v1/admin/live")
async def admin_live_feed(websocket: WebSocket):
    """
    Admin paneli canlı bildirim akışı.
    
    Admin paneli bu WebSocket'e bağlanarak gerçek zamanlı uyarıları alır.
    JWT token ile doğrulanır.
    """
    await websocket.accept()

    # === Auth ===
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        token = auth_msg.get("token", "")

        payload = decode_jwt_token(token)
        if payload is None:
            await websocket.send_json({"error": "Geçersiz token"})
            await websocket.close(code=4001)
            return

        await websocket.send_json({"status": "authenticated", "user": payload.get("sub")})
        logger.info(f"Admin WebSocket bağlantısı: {payload.get('sub')}")

    except asyncio.TimeoutError:
        await websocket.close(code=4002)
        return

    # Admin bağlantılar listesine ekle
    _admin_connections.add(websocket)

    # === Redis Pub/Sub dinleme ===
    try:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe("vektia:alerts:live")

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )

            if message and message["type"] == "message":
                try:
                    await websocket.send_text(message["data"])
                except Exception:
                    break

            # Heartbeat (bağlantı canlı mı kontrol)
            try:
                await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.01
                )
            except asyncio.TimeoutError:
                pass  # Beklenen — heartbeat timeout

    except WebSocketDisconnect:
        logger.info("Admin WebSocket bağlantısı kapandı")
    finally:
        _admin_connections.discard(websocket)
        try:
            await pubsub.unsubscribe("vektia:alerts:live")
        except Exception:
            pass
