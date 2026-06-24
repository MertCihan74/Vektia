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
from vektia.core.temporal import suspicion_tracker
from vektia.core.baseline import player_baseline
from vektia.db.redis_client import get_redis
from vektia.db import repositories as repo
from vektia.db import event_buffer
from vektia.config import get_settings
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
    # Faz 4 — shadow mod: "aksiyon alsaydım" sayaçları (gerçek aksiyon YOK)
    "shadow_would_flag": 0,
    "shadow_would_confirm": 0,
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
        
    # Olay sayacı: hot-path'te Postgres'e YAZMA. Sayaç Redis'te biriktirilir,
    # bir arka-plan görevi (event_buffer.flush_pending_events) periyodik olarak
    # toplu yazar + oyuncu satırını oluşturur. Yüksek hacimde darboğazı kaldırır.
    await event_buffer.record_event(event.client_id, event.player_id, event.server_id)

    # ═══════════════════════════════════════════════
    # WHITELIST (Faz 3) — admin onaylı false-positive düzeltmesi
    # ═══════════════════════════════════════════════
    # Admin bir oyuncuyu "whitelisted" yaptıysa o oyuncu artık ASLA flag/ban üretmez.
    # Kontrol Redis set'inden O(1) yapılır (admin endpoint set'i besler; başlangıçta
    # DB'den senkronlanır). Eski şüphe kanıtını da temizleyip temiz dönüyoruz.
    if await event_buffer.is_whitelisted(event.player_id):
        await suspicion_tracker.reset(event.client_id, event.player_id, event.action_type)
        _stats["clean_events"] += 1
        return AnalysisResult(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=0,
            risk_level=RiskLevel.CLEAN,
            risk_score=0.0,
            flagged=False,
            details={"status": "whitelisted"},
        )

    if not window_data.has_enough_data:
        _stats["insufficient_data"] += 1
        
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

    # ═══════════════════════════════════════════════
    # KATMAN 2.5: Zamansal Kanıt Biriktirme (Faz 1 — Yanlış Pozitif Azaltma)
    # ═══════════════════════════════════════════════
    # Tek bir pencere ASLA tek başına flag/ban üretmez. Pencere riski zaman
    # içinde söndürmeli bir kanıt skorunda birikir; ancak sürdürülen kanıt
    # oluşunca (confirm eşiği) kesin karara izin verilir. İzole/şanslı tek bir
    # şüpheli pencere, sonraki temiz pencerelerde hızla söner ve flag üretmez.
    #
    # Faz 3: Per-player baseline. Oyuncunun temiz geçmişinden bir güven (trust)
    # skoru üret; güvenilen oyuncunun şüpheli pencereleri kanıta DAHA AZ katkı
    # yapsın (leniency). Kalıcı gerçek oyuncuda FP daha da düşer.
    trust_info = await player_baseline.observe(
        event.client_id, event.player_id, event.action_type, stats_result.risk_level
    )
    decision = await suspicion_tracker.record(
        event.client_id, event.player_id, event.action_type, stats_result.risk_level,
        leniency=trust_info.leniency,
    )

    # Yetersiz kanıt → temiz say, hiçbir ek işlem yapma (yalnızca izle)
    if decision.tier == RiskLevel.CLEAN:
        _stats["clean_events"] += 1
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
                "window_risk": stats_result.risk_level.value,
                "temporal_evidence": round(decision.evidence, 3),
                "trust": round(trust_info.trust, 3),
            },
        )

    # ═══════════════════════════════════════════════
    # Faz 4 — SHADOW MOD: kararı yalnızca ÖLÇ, aksiyon alma
    # ═══════════════════════════════════════════════
    # Yeni eşikleri canlıda, gerçek oyuncuyu etkilemeden ölçmek için. Pipeline
    # kararı hesaplandı ama flag/ML/ban YAPILMAZ; sadece "ne yapardım" sayılır.
    if get_settings().shadow_mode:
        _stats["shadow_would_flag"] += 1
        if decision.tier == RiskLevel.CONFIRMED:
            _stats["shadow_would_confirm"] += 1
        logger.info(
            f"[SHADOW] would-flag: client={event.client_id} player={event.player_id} "
            f"tier={decision.tier.value} evidence={decision.evidence:.2f} (aksiyon yok)"
        )
        return AnalysisResult(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=2,
            risk_level=RiskLevel.CLEAN,   # gerçek sonuç: aksiyon alınmadı
            risk_score=stats_result.risk_score,
            std_deviation=stats_result.std_deviation,
            flagged=False,
            details={
                "shadow": True,
                "would_be_tier": decision.tier.value,
                "temporal_evidence": round(decision.evidence, 3),
                "trust": round(trust_info.trust, 3),
                "window_risk": stats_result.risk_level.value,
            },
        )

    # ═══════════════════════════════════════════════
    # Sürdürülen kanıt (SUSPICIOUS / CONFIRMED tier) → ML kuyruğu + flag
    # ═══════════════════════════════════════════════
    _stats["suspicious_events"] += 1

    # Şüpheli oyuncuyu ML worker kuyruğuna ekle (ML nihai kararı verir)
    await _enqueue_for_ml(event.client_id, event.player_id, stats_result, decision)

    # Şüpheli uyarısı oluştur
    await _create_alert(event.client_id, event.player_id, stats_result, layer=2, decision=decision)

    # DB: Flagged olarak işaretle ve tespiti logla
    try:
        await repo.get_or_create_player(event.client_id, event.player_id, event.server_id)
        await repo.update_player_status(
            client_id=event.client_id,
            player_id=event.player_id,
            status="flagged",
            risk_level=decision.tier.value,
            risk_score=stats_result.risk_score,
        )
        await repo.log_detection(
            client_id=event.client_id,
            player_id=event.player_id,
            layer=2,
            risk_level=decision.tier.value,
            risk_score=stats_result.risk_score,
            std_deviation=stats_result.std_deviation,
        )
    except Exception as e:
        logger.error(f"Flagged DB update failed: {e}")

    return AnalysisResult(
        client_id=event.client_id,
        player_id=event.player_id,
        layer=2,
        risk_level=decision.tier,
        risk_score=stats_result.risk_score,
        std_deviation=stats_result.std_deviation,
        flagged=True,
        details={
            "std_deviation": stats_result.std_deviation,
            "cv": stats_result.coefficient_of_variation,
            "entropy": stats_result.entropy,
            "autocorrelation": stats_result.autocorrelation,
            "window_risk": stats_result.risk_level.value,
            "temporal_evidence": round(decision.evidence, 3),
            "trust": round(trust_info.trust, 3),
            "leniency": round(trust_info.leniency, 3),
            "sustained": decision.sustained,
            "queued_for_ml": True,
        },
    )


async def _enqueue_for_ml(client_id: int, player_id: str, stats_result, decision=None) -> None:
    """Şüpheli oyuncuyu ML worker kuyruğuna ekler."""
    try:
        redis = await get_redis()

        ml_task = {
            "client_id": client_id,
            "player_id": player_id,
            "features": stats_result.feature_vector,
            "risk_score": stats_result.risk_score,
            "std_deviation": stats_result.std_deviation,
            "temporal_evidence": round(decision.evidence, 3) if decision else None,
            "temporal_tier": decision.tier.value if decision else None,
            "sustained": decision.sustained if decision else None,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

        await redis.lpush("vektia:ml_queue", json.dumps(ml_task))
        await redis.sadd(f"vektia:client:{client_id}:flagged:suspicious", player_id)

        logger.info(f"ML kuyruğuna eklendi: client={client_id} player={player_id} (risk: {stats_result.risk_score:.2f})")
    except Exception as e:
        logger.error(f"ML kuyruk hatası: {e}")


async def _create_alert(client_id: int, player_id: str, stats_result, layer: int, decision=None) -> None:
    """Yeni uyarı oluşturur ve Redis'e kaydeder."""
    try:
        redis = await get_redis()

        alert = AlertEvent(
            alert_id=str(uuid.uuid4()),
            player_id=player_id,
            risk_level=decision.tier if decision else stats_result.risk_level,
            risk_score=stats_result.risk_score,
            layer=layer,
            details={
                "std_deviation": stats_result.std_deviation,
                "cv": stats_result.coefficient_of_variation,
                "entropy": stats_result.entropy,
                "autocorrelation": stats_result.autocorrelation,
                "window_risk": stats_result.risk_level.value,
                "temporal_evidence": round(decision.evidence, 3) if decision else None,
                "sustained": decision.sustained if decision else None,
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
