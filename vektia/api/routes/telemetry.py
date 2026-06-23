"""
Vektia Telemetry API

Oyun sunucularından gelen telemetri verilerini alan endpoint'ler.
API key ile korunur. Hem tekil hem toplu (batch) olay alımını destekler.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from vektia.core.models import TelemetryEvent, TelemetryBatch, AnalysisResult
from vektia.core.pipeline import process_event
from vektia.api.middleware import verify_api_key, telemetry_rate_limiter
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])


@router.post("/event", response_model=AnalysisResult)
async def receive_event(
    event: TelemetryEvent,
    request: Request,
    client_id: int = Depends(verify_api_key),
):
    """
    Tek bir telemetri olayını alır ve işler.
    
    Oyun sunucusu her oyuncu eylemi (vurma, tıklama, hareket, ticaret)
    gerçekleştiğinde bu endpoint'e veri gönderir.
    """
    # Rate limiting (şimdilik IP bazlı, müşteri bazlı yapılabilir)
    client_ip = request.client.host if request.client else "unknown"
    if not telemetry_rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit aşıldı")

    event.client_id = client_id
    result = await process_event(event)
    return result


@router.post("/batch", response_model=list[AnalysisResult])
async def receive_batch(
    batch: TelemetryBatch,
    request: Request,
    client_id: int = Depends(verify_api_key),
):
    """
    Toplu telemetri olaylarını alır ve işler.
    
    Performans optimizasyonu: Oyun sunucusu olayları biriktirir ve
    tek bir istekte toplu gönderir (örn: her 100ms'de veya 10 olayda bir).
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not telemetry_rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit aşıldı")

    results = []
    for event in batch.events:
        # Server ID'yi batch'ten ata (event'te yoksa)
        if event.server_id is None:
            event.server_id = batch.server_id
        
        event.client_id = client_id
        result = await process_event(event)
        results.append(result)

    return results
