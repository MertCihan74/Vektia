"""
Vektia Layer 1 — Redis Sliding Window Filter

Katmanlı Elek'in ilk katmanı. Milyonlarca oyuncudan gelen telemetri
verisini RAM'i şişirmeden anlık olarak yönetir.

Her oyuncu için sadece son N (varsayılan 20) eylem hafızada tutulur.
Eski veriler Redis Lua scripti ile atomik olarak silinir.
"""

from vektia.db.redis_client import get_redis, execute_lua
from vektia.core.models import TelemetryEvent, WindowData, ActionType, Vector3
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


class SlidingWindowFilter:
    """
    Katman 1: Sliding Window ile veri toplama ve RAM koruma.
    
    Her oyuncunun eylem tipine göre ayrı bir pencere tutulur.
    Örn: player:abc:clicks:hit, player:abc:clicks:move
    """

    def _get_key(self, client_id: int, player_id: str, action_type: ActionType) -> str:
        """Redis key formatı: vektia:client:{client_id}:player:{id}:clicks:{action_type}"""
        return f"vektia:client:{client_id}:player:{player_id}:clicks:{action_type.value}"

    async def process(self, event: TelemetryEvent) -> WindowData:
        """
        Yeni telemetri olayını işler.
        
        1. Timestamp'i sliding window'a ekler
        2. Window'u MAX_WINDOW boyutunda tutar
        3. Yeterli veri toplandıysa analiz için hazır olduğunu bildirir
        
        Args:
            event: Gelen telemetri olayı
            
        Returns:
            WindowData — pencere verisi ve analiz hazırlığı durumu
        """
        settings = get_settings()
        key = self._get_key(event.client_id, event.player_id, event.action_type)

        try:
            # Veri formatı: "timestamp|x|y" veya "timestamp"
            data_str = str(event.timestamp)
            if event.coords:
                data_str = f"{event.timestamp}|{event.coords.x}|{event.coords.y}"

            # Lua scripti ile atomik sliding window işlemi
            raw_data_list = await execute_lua(
                "sliding_window",
                keys=[key],
                args=[
                    data_str,
                    str(settings.max_window),
                    str(settings.player_ttl_seconds),
                ],
            )

            timestamps = []
            coords_list = []
            for item in raw_data_list:
                parts = item.split("|")
                timestamps.append(float(parts[0]))
                if len(parts) >= 3:
                    coords_list.append(Vector3(x=float(parts[1]), y=float(parts[2]), z=0.0))
                else:
                    coords_list.append(None)

            return WindowData(
                client_id=event.client_id,
                player_id=event.player_id,
                timestamps=timestamps,
                action_type=event.action_type,
                has_enough_data=len(timestamps) >= settings.max_window,
                window_size=len(timestamps),
                coords_list=coords_list,
            )

        except ValueError:
            # Lua scripti yüklenmemişse fallback: saf Redis komutları
            logger.warning("Lua script bulunamadı, fallback moduna geçiliyor")
            return await self._fallback_process(event)

    async def _fallback_process(self, event: TelemetryEvent) -> WindowData:
        """Lua script yoksa saf Redis komutlarıyla çalışan fallback."""
        settings = get_settings()
        redis = await get_redis()
        key = self._get_key(event.client_id, event.player_id, event.action_type)

        data_str = str(event.timestamp)
        if event.coords:
            data_str = f"{event.timestamp}|{event.coords.x}|{event.coords.y}"

        pipe = redis.pipeline(transaction=True)
        pipe.lpush(key, data_str)
        pipe.ltrim(key, 0, settings.max_window - 1)
        pipe.expire(key, settings.player_ttl_seconds)
        pipe.lrange(key, 0, -1)
        results = await pipe.execute()

        raw_data_list = results[3]  # lrange sonucu
        timestamps = []
        coords_list = []
        for item in raw_data_list:
            parts = item.split("|")
            timestamps.append(float(parts[0]))
            if len(parts) >= 3:
                coords_list.append(Vector3(x=float(parts[1]), y=float(parts[2]), z=0.0))
            else:
                coords_list.append(None)

        return WindowData(
            client_id=event.client_id,
            player_id=event.player_id,
            timestamps=timestamps,
            action_type=event.action_type,
            has_enough_data=len(timestamps) >= settings.max_window,
            window_size=len(timestamps),
            coords_list=coords_list,
        )

    async def get_player_window(
        self, client_id: int, player_id: str, action_type: ActionType
    ) -> list[float]:
        """Bir oyuncunun mevcut pencere verisini döndürür (okuma amaçlı)."""
        redis = await get_redis()
        key = self._get_key(client_id, player_id, action_type)
        raw = await redis.lrange(key, 0, -1)
        return [float(t) for t in raw]

    async def clear_player_data(self, client_id: int, player_id: str) -> None:
        """Bir oyuncunun tüm pencere verilerini siler."""
        redis = await get_redis()
        for action_type in ActionType:
            key = self._get_key(client_id, player_id, action_type)
            await redis.delete(key)


# Modül seviyesi singleton
sliding_window_filter = SlidingWindowFilter()
