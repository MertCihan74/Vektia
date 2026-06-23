"""
Vektia ML Background Worker

Redis kuyruğundan şüpheli oyuncu verilerini çekip
Isolation Forest modeli ile kesin anomali tespiti yapar.

Periyodik olarak çalışır (varsayılan: her 30 saniye).
Ana API sunucusundan bağımsız bir süreç olarak da çalıştırılabilir.
"""

import asyncio
import json

from vektia.core.layer3_ml import ml_detector
from vektia.core.models import StatsResult, RiskLevel
from vektia.db.redis_client import init_redis, get_redis, close_redis
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


async def process_ml_queue() -> int:
    """
    ML kuyruğundaki tüm şüpheli oyuncuları işler.
    
    Returns:
        İşlenen oyuncu sayısı
    """
    redis = await get_redis()
    processed = 0

    while True:
        # Kuyruktan bir görev çek (blocking olmadan)
        raw_task = await redis.rpop("vektia:ml_queue")
        if raw_task is None:
            break

        try:
            task = json.loads(raw_task)
            client_id = task.get("client_id", 0)
            player_id = task["player_id"]
            features = task["features"]

            # StatsResult'ı features'dan yeniden oluştur
            stats_result = StatsResult(
                client_id=client_id,
                player_id=player_id,
                std_deviation=features[0] if len(features) > 0 else 0.0,
                coefficient_of_variation=features[1] if len(features) > 1 else 0.0,
                entropy=features[2] if len(features) > 2 else 0.0,
                autocorrelation=features[3] if len(features) > 3 else 0.0,
                mean_delta=features[4] if len(features) > 4 else 0.0,
                median_delta=features[5] if len(features) > 5 else 0.0,
                risk_score=task.get("risk_score", 0.5),
            )

            # ML modeli ile tahmin
            anomaly_score, risk_level = ml_detector.predict(stats_result)

            # Sonucu Redis'e kaydet
            result_data = {
                "player_id": player_id,
                "anomaly_score": anomaly_score,
                "risk_level": risk_level.value,
                "ml_analyzed": True,
            }

            if risk_level in (RiskLevel.CONFIRMED, RiskLevel.HIGH):
                # Kesin bot — onay kuyruğuna ekle
                await redis.sadd(f"vektia:client:{client_id}:flagged:confirmed", player_id)
                await redis.hset(
                    f"vektia:client:{client_id}:player:{player_id}:ml_result",
                    mapping={
                        "anomaly_score": str(anomaly_score),
                        "risk_level": risk_level.value,
                    },
                )

                # Admin'e canlı bildirim
                await redis.publish(
                    f"vektia:client:{client_id}:alerts:live",
                    json.dumps({
                        "type": "ml_confirmed",
                        "player_id": player_id,
                        "anomaly_score": anomaly_score,
                        "risk_level": risk_level.value,
                    }),
                )

                logger.info(
                    f"[ML WORKER] BOT TESPİT EDİLDİ: {player_id} "
                    f"(skor: {anomaly_score:.4f}, seviye: {risk_level.value})"
                )
            else:
                # Temiz — şüpheli listesinden çıkar
                await redis.srem(f"vektia:client:{client_id}:flagged:suspicious", player_id)
                logger.info(
                    f"[ML WORKER] Temiz: {player_id} "
                    f"(skor: {anomaly_score:.4f})"
                )

            processed += 1

        except Exception as e:
            logger.error(f"ML görev işleme hatası: {e}")

    return processed


async def ml_worker_loop() -> None:
    """
    ML worker ana döngüsü.
    Periyodik olarak kuyruğu kontrol eder ve işler.
    """
    settings = get_settings()

    logger.info(
        f"ML Worker başlatıldı (periyot: {settings.ml_batch_interval_seconds}s)"
    )

    while True:
        try:
            processed = await process_ml_queue()
            if processed > 0:
                logger.info(f"ML batch tamamlandı: {processed} oyuncu işlendi")
        except Exception as e:
            logger.error(f"ML worker döngü hatası: {e}")

        await asyncio.sleep(settings.ml_batch_interval_seconds)


async def main():
    """Bağımsız süreç olarak çalıştırma."""
    await init_redis()
    try:
        await ml_worker_loop()
    finally:
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
