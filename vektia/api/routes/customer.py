"""
Vektia Customer API

Müşteri (Oyun Stüdyosu) paneli için özel endpoint'ler.
Sadece kendi client_id'lerine ait verileri okuyabilirler.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone

from vektia.api.middleware import verify_jwt_token, register_rate_limiter, login_rate_limiter
from vektia.core.models import TokenResponse
from vektia.db import repositories as repo
from vektia.utils.security import create_jwt_token
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/customer", tags=["Customer"])


# ============================================
# Request Models
# ============================================

class CustomerLoginRequest(BaseModel):
    api_key: str

class CustomerSendOtpRequest(BaseModel):
    name: str
    email: EmailStr
    tier: str = "premium"

class CustomerVerifyOtpRequest(BaseModel):
    name: str
    email: EmailStr
    tier: str = "premium"
    otp_code: str

class PlayerStatusUpdateRequest(BaseModel):
    status: str
    ban_reason: str | None = None


# ============================================
# Auth Endpoints
# ============================================

FORBIDDEN_DOMAINS = {"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "yandex.com", "tempmail.com"}

@router.post("/register/send-otp")
async def customer_send_otp(request: CustomerSendOtpRequest, req: Request):
    """Kayıt için ilk adım: E-postaya OTP kodu gönderir."""
    ip_addr = req.client.host if req.client else "unknown"
    
    if not register_rate_limiter.is_allowed(ip_addr):
        raise HTTPException(status_code=429, detail="Çok fazla kayıt isteği. Lütfen daha sonra tekrar deneyin.")

    domain = request.email.split('@')[-1].lower()
    if domain in FORBIDDEN_DOMAINS:
        raise HTTPException(status_code=400, detail="Lütfen kişisel veya geçici e-posta yerine kurumsal bir e-posta adresi kullanın.")
    
    if request.tier == "free":
        has_free = await repo.check_domain_free_tier(domain)
        if has_free:
            raise HTTPException(status_code=400, detail=f"'{domain}' alan adı ile zaten bir ücretsiz deneme kullanılmış. Lütfen Premium pakete geçin.")

    # MOCK EMAIL GÖNDERİMİ (Sadece konsola loglar)
    otp_code = await repo.create_verification_otp(request.email)
    logger.info(f"[MOCK MAIL] Alıcı: {request.email} | Doğrulama Kodu: {otp_code}")
    
    return {"message": "Doğrulama kodu e-posta adresinize gönderildi."}


@router.post("/register/verify-otp")
async def customer_verify_otp(request: CustomerVerifyOtpRequest):
    """Kayıt için ikinci adım: OTP'yi doğrular ve müşteriyi oluşturur."""
    is_valid = await repo.verify_otp(request.email, request.otp_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Geçersiz veya süresi dolmuş doğrulama kodu.")

    # Müşteriyi veritabanında oluştur
    if request.tier == "free":
        client = await repo.create_client(name=request.name, email=request.email, tier="free", billing_day=1)
        return {
            "status": "success",
            "tier": "free",
            "message": "Kayıt başarılı. API Key'inizi güvenli bir yere kaydedin.",
            "api_key": client.api_key
        }
    else:
        # Premium için hesabı inaktif başlat (ödeme bekleniyor)
        client = await repo.create_client(name=request.name, email=request.email, tier="premium", billing_day=1)
        client.is_active = False # Ödeme gelene kadar pasif
        # Not: Aslında create_client is_active=True dönüyor, bunu güncellemeliyiz.
        await repo.update_client(client.id, client.name, client.tier, client.billing_day, client.is_overdue, False)
        
        settings = get_settings()
        # Lemon Squeezy Checkout URL'ini mockluyoruz (gerçek entegrasyonda API'den alınır)
        checkout_url = f"{settings.API_BASE_URL}/admin/customer_login.html?checkout=mock&client_id={client.id}"
        
        return {
            "status": "pending_payment",
            "tier": "premium",
            "message": "Doğrulama başarılı. Ödeme adımına yönlendiriliyorsunuz.",
            "checkout_url": checkout_url
        }

@router.post("/login", response_model=TokenResponse)
async def customer_login(request: CustomerLoginRequest, req: Request):
    """Müşteri girişi — API Key ile JWT token döndürür."""
    ip_addr = req.client.host if req.client else "unknown"

    if not login_rate_limiter.is_allowed(ip_addr):
        raise HTTPException(status_code=429, detail="Çok fazla başarısız giriş denemesi. Güvenlik nedeniyle IP adresiniz geçici olarak engellendi.")

    client = await repo.get_client_by_api_key(request.api_key)

    if client is None:
        raise HTTPException(status_code=401, detail="Geçersiz API Key")

    settings = get_settings()
    token = create_jwt_token({
        "sub": str(client.id),
        "role": "customer",
        "name": client.name,
        "tier": client.tier
    })

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiration_minutes * 60,
    )


# ============================================
# Dashboard
# ============================================

@router.get("/dashboard")
async def get_dashboard(auth: dict = Depends(verify_jwt_token)):
    """Müşteriye özel dashboard özet istatistikleri ve grafik verileri."""
    if auth.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Yetkisiz erişim")
        
    client_id = int(auth.get("sub"))
    
    db_stats = await repo.get_dashboard_stats(client_id)
    chart_data = await repo.get_chart_data(client_id)
    
    client = await repo.get_client_by_id(client_id)

    return {
        **db_stats,
        "chart_data": chart_data,
        "client_name": auth.get("name"),
        "tier": auth.get("tier"),
        "billing": {
            "status": client.subscription_status if client else "inactive",
            "end_date": client.subscription_end_date.isoformat() if client and client.subscription_end_date else None,
            "created_at": client.created_at.isoformat() if client else None
        }
    }

def _mask_player_id(player_id: str) -> str:
    """Free tier kullanıcılar için Player ID'yi gizler."""
    if len(player_id) <= 4:
        return player_id[0] + "***"
    return player_id[:4] + "***"


@router.delete("/account")
async def delete_customer_account(auth: dict = Depends(verify_jwt_token)):
    """Müşteri hesabını siler. Aktif premium üyelik varsa engeller."""
    if auth.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Yetkisiz erişim")
        
    client_id = int(auth.get("sub"))
    client = await repo.get_client_by_id(client_id)
    
    if not client:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
        
    if client.tier == "premium" and client.subscription_status == "active":
        raise HTTPException(
            status_code=400, 
            detail="Lütfen hesabınızı silmeden önce Premium aboneliğinizi sonlandırın."
        )
        
    # Her şey uygunsa müşteriyi sil
    success = await repo.delete_client(client_id)
    if not success:
        raise HTTPException(status_code=500, detail="Hesap silinirken bir hata oluştu")
        
    return {"message": "Hesabınız başarıyla silinmiştir."}


# ============================================
# Player Management
# ============================================

@router.get("/players")
async def list_players(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "risk_score",
    auth: dict = Depends(verify_jwt_token),
):
    """Müşteriye özel oyuncu listesi."""
    if auth.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Yetkisiz erişim")
        
    client_id = int(auth.get("sub"))
    
    players, total = await repo.get_players(
        status=status, client_id=client_id, limit=limit, offset=offset, sort_by=sort_by
    )

    tier = auth.get("tier")

    # Deduplicate players by player_id, keeping the one with the highest risk_score
    unique_players = {}
    for p in players:
        if p.player_id not in unique_players or p.risk_score > unique_players[p.player_id].risk_score:
            unique_players[p.player_id] = p
            
    deduped_players = list(unique_players.values())

    return {
        "players": [
            {
                "player_id": p.player_id if tier == "premium" else _mask_player_id(p.player_id),
                "status": p.status,
                "risk_level": p.risk_level,
                "risk_score": p.risk_score,
                "total_events": p.total_events,
                "flagged_count": p.flagged_count,
                "last_seen": p.last_seen.isoformat() if p.last_seen else None,
            }
            for p in deduped_players
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/alerts")
async def get_alerts(
    limit: int = 50,
    player_id: str | None = None,
    auth: dict = Depends(verify_jwt_token),
):
    """Müşteriye özel son uyarıları listele. İsteğe bağlı olarak belirli bir oyuncunun uyarılarını getirir."""
    if auth.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Yetkisiz erişim")
        
    client_id = int(auth.get("sub"))
    
    logs = await repo.get_recent_detections(limit, client_id)
    
    tier = auth.get("tier")
    
    alerts = []
    for log in logs:
        # Eğer player_id filtresi varsa ve eşleşmiyorsa atla
        # Unmasked ve masked player_id ikisine de bakmalıyız
        if player_id:
            masked = _mask_player_id(log.player_id)
            if log.player_id != player_id and masked != player_id:
                continue
                
        alerts.append({
            "player_id": log.player_id if tier == "premium" else _mask_player_id(log.player_id),
            "layer": log.layer,
            "risk_level": log.risk_level,
            "score": log.risk_score,
            "detected_at": log.detected_at.isoformat() if log.detected_at else None
        })

    return {"alerts": alerts, "count": len(alerts)}


@router.post("/players/{player_id}/status")
async def update_player_status(player_id: str, request: PlayerStatusUpdateRequest, auth: dict = Depends(verify_jwt_token)):
    """Müşterinin kendi oyuncusunu banlaması/beyaz listeye alması (Sadece Premium)."""
    tier = auth.get("tier", "premium")
    if tier == "free":
        raise HTTPException(status_code=403, detail="Bu işlem sadece Premium üyeler içindir. Lütfen paketinizi yükseltin.")

    client_id = int(auth["sub"])
    player = await repo.update_player_status(
        client_id=client_id,
        player_id=player_id,
        status=request.status,
        ban_reason=request.ban_reason,
        banned_by="customer_dashboard"
    )
    
    if not player:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı veya size ait değil.")
        
    return {"message": "Oyuncu durumu güncellendi", "player_id": player.player_id, "status": player.status}


class UpdateSettingsRequest(BaseModel):
    auto_ban_enabled: bool
    auto_ban_high_risk: bool
    auto_ban_suspicious: bool

@router.get("/settings")
async def get_customer_settings(auth: dict = Depends(verify_jwt_token)):
    """Müşterinin ayarlarını getirir."""
    client_id = int(auth["sub"])
    settings = await repo.get_client_settings(client_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    return settings

@router.put("/settings")
async def update_customer_settings(request: UpdateSettingsRequest, auth: dict = Depends(verify_jwt_token)):
    """Müşterinin ayarlarını günceller (Sadece Premium)."""
    tier = auth.get("tier", "premium")
    if tier == "free":
        raise HTTPException(status_code=403, detail="Ayarları değiştirmek için Premium pakete geçmelisiniz.")
        
    client_id = int(auth["sub"])
    success = await repo.update_client_settings(
        client_id, 
        request.auto_ban_enabled, 
        request.auto_ban_high_risk, 
        request.auto_ban_suspicious
    )
    if not success:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    return {"message": "Ayarlar güncellendi"}
