from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from vektia.api.middleware import verify_jwt_token
from vektia.db import repositories as repo
from vektia.utils.logger import get_logger
from vektia.config import get_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])

class CheckoutRequest(BaseModel):
    tier: str = "premium"

@router.post("/create-checkout-session")
async def create_checkout_session(request: CheckoutRequest, token: dict = Depends(verify_jwt_token)):
    """Mevcut bir hesabı Premium'a geçirmek için Lemon Squeezy Checkout URL'i oluşturur."""
    client_id = int(token["sub"])
    client = await repo.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı.")
    
    settings = get_settings()
    checkout_url = f"{settings.API_BASE_URL}/admin/customer_login.html?checkout=mock&client_id={client_id}"
    
    return {
        "checkout_url": checkout_url
    }

@router.post("/cancel-subscription")
async def cancel_subscription(token: dict = Depends(verify_jwt_token)):
    """Müşterinin aktif Premium aboneliğini iptal eder (Mock)."""
    client_id = int(token["sub"])
    client = await repo.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı.")
    
    if client.tier != "premium" or client.subscription_status != "active":
        raise HTTPException(status_code=400, detail="İptal edilecek aktif bir Premium abonelik bulunamadı.")
        
    # Mock Lemon Squeezy API call here
    # Local update
    client = await repo.update_client_subscription(
        client_id=client.id,
        ls_customer_id=client.ls_customer_id or "",
        subscription_id=client.subscription_id or "",
        status="canceled",
        end_date=client.subscription_end_date
    )
    
    return {"message": "Aboneliğiniz iptal edildi. Süreniz dolana kadar Premium ayrıcalıklarından faydalanabilirsiniz."}

@router.post("/webhook/lemonsqueezy")
async def lemonsqueezy_webhook(req: Request):
    """Lemon Squeezy'den gelen ödeme başarılı veya abonelik iptal bildirimlerini işler."""
    # In a real app, verify the webhook signature here using hmac and LEMON_SQUEEZY_WEBHOOK_SECRET
    payload = await req.json()
    logger.info(f"Lemon Squeezy Webhook received: {payload.get('meta', {}).get('event_name')}")
    
    # Mock processing
    return {"status": "success"}
