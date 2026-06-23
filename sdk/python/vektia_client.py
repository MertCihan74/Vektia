"""
Vektia Python Telemetry Client SDK

Oyun sunucuları için asenkron telemetri istemcisi.
HTTP batch veya WebSocket üzerinden Vektia API'sine veri gönderir.

Kullanım:
    from vektia_client import VektiaClient
    
    client = VektiaClient("http://vektia-server:8000", "your-api-key")
    await client.connect()
    await client.track("player_123", "hit", timestamp=1234567890.0)
    await client.close()
"""

import asyncio
import json
import time
from typing import Optional

import httpx

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class VektiaClient:
    """Vektia Telemetry SDK — Python Implementation."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        server_id: str = "python_server",
        batch_size: int = 10,
        batch_interval: float = 0.1,
        use_websocket: bool = True,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.server_id = server_id
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.use_websocket = use_websocket and HAS_WEBSOCKETS

        self._queue: list[dict] = []
        self._ws = None
        self._flush_task: Optional[asyncio.Task] = None
        self._connected = False

    async def connect(self) -> None:
        """Bağlantıyı başlat (WebSocket veya HTTP)."""
        if self.use_websocket:
            await self._connect_ws()
        
        # Periyodik flush görevi
        self._flush_task = asyncio.create_task(self._flush_loop())
        print(f"[Vektia SDK] Bağlandı → {self.api_url} (server: {self.server_id})")

    async def _connect_ws(self) -> None:
        """WebSocket bağlantısı kur."""
        ws_url = self.api_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/v1/telemetry/stream"

        try:
            self._ws = await websockets.connect(ws_url)
            # Auth
            await self._ws.send(json.dumps({
                "auth": self.api_key,
                "server_id": self.server_id,
            }))
            response = json.loads(await self._ws.recv())
            if response.get("status") == "authenticated":
                self._connected = True
            else:
                raise ConnectionError(f"Auth failed: {response}")
        except Exception as e:
            print(f"[Vektia SDK] WebSocket hatası, HTTP'ye geçiliyor: {e}")
            self.use_websocket = False
            self._ws = None

    async def track(
        self,
        player_id: str,
        action_type: str,
        timestamp: float | None = None,
        coords: dict | None = None,
    ) -> None:
        """
        Telemetri olayı kaydet.
        
        Args:
            player_id: Oyuncu ID
            action_type: hit, click, move, trade, interact, cast
            timestamp: Milisaniye (None ise otomatik)
            coords: {"x": float, "y": float, "z": float}
        """
        event = {
            "player_id": player_id,
            "action_type": action_type,
            "timestamp": timestamp or (time.time() * 1000),
            "server_id": self.server_id,
        }
        if coords:
            event["coords"] = coords

        self._queue.append(event)

        if len(self._queue) >= self.batch_size:
            await self._flush()

    async def _flush(self) -> None:
        """Kuyruktaki olayları gönder."""
        if not self._queue:
            return

        events = self._queue.copy()
        self._queue.clear()

        if self.use_websocket and self._ws and self._connected:
            await self._flush_ws(events)
        else:
            await self._flush_http(events)

    async def _flush_ws(self, events: list[dict]) -> None:
        """WebSocket üzerinden gönder."""
        try:
            for event in events:
                await self._ws.send(json.dumps(event))
        except Exception as e:
            print(f"[Vektia SDK] WS flush hatası: {e}")
            # Fallback HTTP
            await self._flush_http(events)

    async def _flush_http(self, events: list[dict]) -> None:
        """HTTP batch olarak gönder."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/api/v1/telemetry/batch",
                    json={"events": events, "server_id": self.server_id},
                    headers={
                        "X-Vektia-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=5.0,
                )
                if response.status_code != 200:
                    print(f"[Vektia SDK] HTTP hatası: {response.status_code}")
        except Exception as e:
            print(f"[Vektia SDK] HTTP flush hatası: {e}")

    async def _flush_loop(self) -> None:
        """Periyodik flush döngüsü."""
        while True:
            await asyncio.sleep(self.batch_interval)
            await self._flush()

    async def close(self) -> None:
        """Bağlantıyı kapat."""
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush()  # Son olayları gönder
        if self._ws:
            await self._ws.close()
        print("[Vektia SDK] Bağlantı kapatıldı")


# ============================================
# Convenience: Senkron Wrapper
# ============================================

class VektiaClientSync:
    """Senkron (non-async) wrapper. Thread-safe değildir."""

    def __init__(self, api_url: str, api_key: str, **kwargs):
        self._client = VektiaClient(api_url, api_key, use_websocket=False, **kwargs)
        self._loop = asyncio.new_event_loop()

    def track(self, player_id: str, action_type: str, **kwargs) -> None:
        self._loop.run_until_complete(self._client.track(player_id, action_type, **kwargs))

    def close(self) -> None:
        self._loop.run_until_complete(self._client.close())
        self._loop.close()
