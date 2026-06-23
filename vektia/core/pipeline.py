"""
Vektia Pipeline Orchestrator

Katmanlı Elek pipeline'ını yöneten ana orkestratör.
Telemetri olaylarını sırasıyla 3 katmandan geçirerek nihai sonucu üretir.

Akış:
  Event → [Katman 1: Sliding Window] → [Katman 2: İstatistik] → Sonuç
                                                         ↓ (Şüpheli ise)
                                              [Redis Queue → ML Worker]
"""

import asyncio
from datetime import datetime, timezone

from vektia.core.models import (
    TelemetryEvent,
    AnalysisResult,
    RiskLevel,
    AlertEvent,
)
from vektia.core.layer1_redis import sliding_window_filter
from vektia.core.layer2_stats import statistical_filter
from vektia.db.redis_client import get_redis
from vektia.db import repositories as repo
from vektia.utils.logger import get_logger

import json
import uuid

logger = get_logger(__name__)

# Pipeline istatistikleri (in-memory counter)
_stats = {
    "total_events": 0,
    "clean_events": 0,
    "suspicious_events": 0,
    "flagged_events": 0,
    "insufficient_data": 0,
}


async def process_event(event: TelemetryEvent) -> AnalysisResult:
    """
    Ana pipeline — tek bir telemetri olayını tüm katmanlardan geçirir.
    
    Args:
        event: Oyun sunucusundan gelen telemetri olayı
        
    Returns:
        AnalysisResult — nihai analiz sonucu
    """
    _stats["total_events"] += 1

    # ═══════════════════════════════════════════════
    # KATMAN 1: Redis Sliding Window
    # ═══════════════════════════════════════════════
    window_data = await sliding_window_filter.process(event)

    if not window_data.has_enough_data:
        _stats["insufficient_data"] += 1
        
        # DB: Sadece event sayısını artır
        try:
            await repo.get_or_create_player(event.client_id, event.player_id, event.server_id)
            await repo.increment_player_events(event.client_id, event.player_id)
        except Exception as e:
            logger.error(f"DB insert failed: {e}")
        
        return AnalysisResult(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=0,
            risk_level=RiskLevel.CLEAN,
            risk_score=0.0,
            flagged=False,
            details={"status": "collecting_data", "window_size": window_data.window_size},
        )

    # ═══════════════════════════════════════════════
    # KATMAN 2: İstatistiksel Standart Sapma Analizi
    # ═══════════════════════════════════════════════
    stats_result = statistical_filter.analyze(window_data)

    if stats_result.risk_level == RiskLevel.CLEAN:
        _stats["clean_events"] += 1
        # Temiz oyuncu — veri akıp gider, hiçbir ek işlem yapılmaz
        return AnalysisResult(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=2,
            risk_level=RiskLevel.CLEAN,
            risk_score=stats_result.risk_score,
            std_deviation=stats_result.std_deviation,
            flagged=False,
            details={
                "std_deviation": stats_result.std_deviation,
                "cv": stats_result.coefficient_of_variation,
                "entropy": stats_result.entropy,
            },
        )

    # ═══════════════════════════════════════════════
    # KATMAN 2.5: Şüpheli → ML Kuyruğuna Ekle
    # ═══════════════════════════════════════════════
    if stats_result.risk_level in (RiskLevel.SUSPICIOUS, RiskLevel.HIGH):
        _stats["suspicious_events"] += 1

        # Şüpheli oyuncuyu ML worker kuyruğuna ekle
        await _enqueue_for_ml(event.client_id, event.player_id, stats_result)

        # Şüpheli uyarısı oluştur
        await _create_alert(event.client_id, event.player_id, stats_result, layer=2)
        
        # DB: Flagged olarak işaretle ve tespiti logla
        try:
            # Önce oyuncunun var olduğundan emin ol (Clean değilse Layer2'de ilk defa da yakalanmış olabilir)
            await repo.get_or_create_player(event.client_id, event.player_id, event.server_id)
            
            await repo.update_player_status(
                client_id=event.client_id,
                player_id=event.player_id,
                status="flagged",
                risk_level=stats_result.risk_level.value,
                risk_score=stats_result.risk_score
            )
            await repo.log_detection(
                client_id=event.client_id,
                player_id=event.player_id,
                layer=2,
                risk_level=stats_result.risk_level.value,
                risk_score=stats_result.risk_score,
                std_deviation=stats_result.std_deviation,
            )
        except Exception as e:
            logger.error(f"Flagged DB update failed: {e}")

        return AnalysisResult(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=2,
            risk_level=stats_result.risk_level,
            risk_score=stats_result.risk_score,
            std_deviation=stats_result.std_deviation,
            flagged=True,
            details={
                "std_deviation": stats_result.std_deviation,
                "cv": stats_result.coefficient_of_variation,
                "entropy": stats_result.entropy,
                "autocorrelation": stats_result.autocorrelation,
                "queued_for_ml": True,
            },
        )

    # LOW risk — izlemeye devam
    _stats["clean_events"] += 1
    return AnalysisResult(
        client_id=event.client_id,
        player_id=event.player_id,
        layer=2,
        risk_level=stats_result.risk_level,
        risk_score=stats_result.risk_score,
        std_deviation=stats_result.std_deviation,
        flagged=False,
        details={
            "std_deviation": stats_result.std_deviation,
            "cv": stats_result.coefficient_of_variation,
        },
    )


async def _enqueue_for_ml(client_id: int, player_id: str, stats_result) -> None:
    """Şüpheli oyuncuyu ML worker kuyruğuna ekler."""
    try:
        redis = await get_redis()

        ml_task = {
            "client_id": client_id,
            "player_id": player_id,
            "features": stats_result.feature_vector,
            "risk_score": stats_result.risk_score,
            "std_deviation": stats_result.std_deviation,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

        await redis.lpush("vektia:ml_queue", json.dumps(ml_task))
        await redis.sadd(f"vektia:client:{client_id}:flagged:suspicious", player_id)

        logger.info(f"ML kuyruğuna eklendi: client={client_id} player={player_id} (risk: {stats_result.risk_score:.2f})")
    except Exception as e:
        logger.error(f"ML kuyruk hatası: {e}")


async def _create_alert(client_id: int, player_id: str, stats_result, layer: int) -> None:
    """Yeni uyarı oluşturur ve Redis'e kaydeder."""
    try:
        redis = await get_redis()

        alert = AlertEvent(
            alert_id=str(uuid.uuid4()),
            player_id=player_id,
            risk_level=stats_result.risk_level,
            risk_score=stats_result.risk_score,
            layer=layer,
            details={
                "std_deviation": stats_result.std_deviation,
                "cv": stats_result.coefficient_of_variation,
                "entropy": stats_result.entropy,
                "autocorrelation": stats_result.autocorrelation,
            },
        )

        # Uyarıyı Redis'te sakla (son 1000 uyarı)
        alert_json = alert.model_dump_json()
        await redis.lpush(f"vektia:client:{client_id}:alerts", alert_json)
        await redis.ltrim(f"vektia:client:{client_id}:alerts", 0, 999)

        # Canlı admin bildirimi için pub/sub
        await redis.publish(f"vektia:client:{client_id}:alerts:live", alert_json)

    except Exception as e:
        logger.error(f"Uyarı oluşturma hatası: {e}")


def get_pipeline_stats() -> dict:
    """Pipeline istatistiklerini döndürür."""
    return _stats.copy()


def reset_pipeline_stats() -> None:
    """Pipeline istatistiklerini sıfırlar."""
    for key in _stats:
        _stats[key] = 0
