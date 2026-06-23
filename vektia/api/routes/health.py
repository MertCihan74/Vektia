"""
Vektia Health Check API

Sistem sağlık kontrolü ve versiyon bilgisi.
"""

import time

from fastapi import APIRouter

from vektia.core.models import HealthResponse
from vektia.db.redis_client import is_redis_healthy
from vektia.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["Health"])

# Uygulama başlangıç zamanı
_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Sistem sağlık kontrolü."""
    settings = get_settings()
    redis_ok = await is_redis_healthy()

    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        version=settings.version,
        redis_connected=redis_ok,
        uptime_seconds=round(time.time() - _start_time, 1),
    )
