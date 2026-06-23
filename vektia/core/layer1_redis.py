"""
Vektia Layer 1 — Redis Sliding Window Filter

Katmanlı Elek'in ilk katmanı. Milyonlarca oyuncudan gelen telemetri
verisini RAM'i şişirmeden anlık olarak yönetir.

Her oyuncu için sadece son N (varsayılan 20) eylem hafızada tutulur.
Eski veriler Redis Lua scripti ile atomik olarak silinir.
"""

from vektia.db.redis_client import get_redis, execute_lua
from vektia.core.models import TelemetryEvent, WindowData, ActionType
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
            # Lua scripti ile atomik sliding window işlemi
            timestamps_raw = await execute_lua(
                "sliding_window",
                keys=[key],
                args=[
                    str(event.timestamp),
                    str(settings.max_window),
                    str(settings.player_ttl_seconds),
                ],
            )

            timestamps = [float(t) for t in timestamps_raw]

            return WindowData(
                client_id=event.client_id,
                player_id=event.player_id,
                timestamps=timestamps,
                action_type=event.action_type,
                has_enough_data=len(timestamps) >= settings.max_window,
                window_size=len(timestamps),
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

        pipe = redis.pipeline(transaction=True)
        pipe.lpush(key, str(event.timestamp))
        pipe.ltrim(key, 0, settings.max_window - 1)
        pipe.expire(key, settings.player_ttl_seconds)
        pipe.lrange(key, 0, -1)
        results = await pipe.execute()

        timestamps_raw = results[3]  # lrange sonucu
        timestamps = [float(t) for t in timestamps_raw]

        return WindowData(
            client_id=event.client_id,
            player_id=event.player_id,
            timestamps=timestamps,
            action_type=event.action_type,
            has_enough_data=len(timestamps) >= settings.max_window,
            window_size=len(timestamps),
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
