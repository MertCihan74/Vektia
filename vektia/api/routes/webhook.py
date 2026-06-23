"""
Vektia Webhook API

Oyun sunucularının webhook URL'lerini kaydetmesi ve yönetmesi için endpoint'ler.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from vektia.api.middleware import verify_api_key
from vektia.db import repositories as repo
from vektia.db.redis_client import get_redis


router = APIRouter(prefix="/api/v1/webhook", tags=["Webhook"])


class WebhookRegisterRequest(BaseModel):
    server_id: str
    url: str
    secret: str | None = None


@router.post("/register")
async def register_webhook(
    request: WebhookRegisterRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Yeni webhook URL'i kaydeder."""
    webhook = await repo.register_webhook(
        server_id=request.server_id,
        url=request.url,
        secret=request.secret,
    )

    # Redis'e de ekle (hızlı erişim için)
    redis = await get_redis()
    await redis.sadd("vektia:webhooks", request.url)

    return {
        "message": "Webhook kaydedildi",
        "webhook_id": webhook.id,
        "url": request.url,
    }


@router.get("/list")
async def list_webhooks(_api_key: str = Depends(verify_api_key)):
    """Kayıtlı webhook'ları listeler."""
    webhooks = await repo.get_active_webhooks()
    return {
        "webhooks": [
            {
                "id": w.id,
                "server_id": w.server_id,
                "url": w.url,
                "is_active": w.is_active,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in webhooks
        ]
    }
