"""
Vektia Admin API

Admin paneli için CRUD endpoint'leri.
JWT token ile korunur.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from vektia.api.middleware import verify_jwt_token
from vektia.core.models import TokenResponse, DashboardStats
from vektia.core.pipeline import get_pipeline_stats
from vektia.db import repositories as repo
from vektia.db.redis_client import get_redis
from vektia.utils.security import create_jwt_token
from vektia.config import get_settings
from vektia.utils.logger import get_logger

import json

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


# ============================================
# Request Models
# ============================================

class LoginRequest(BaseModel):
    username: str
    password: str

class ClientCreateRequest(BaseModel):
    name: str
    tier: str = "premium"
    billing_day: int = 1

class ClientUpdateRequest(BaseModel):
    name: str
    tier: str
    billing_day: int
    is_overdue: bool
    is_active: bool


class BanRequest(BaseModel):
    reason: str = "Bot/Makro tespiti"


class WhitelistRequest(BaseModel):
    reason: str = "False positive düzeltmesi"


# ============================================
# Auth Endpoints
# ============================================

@router.post("/login", response_model=TokenResponse)
async def admin_login(request: LoginRequest):
    """Admin giriş — JWT token döndürür."""
    admin = await repo.authenticate_admin(request.username, request.password)

    if admin is None:
        raise HTTPException(status_code=401, detail="Geçersiz kullanıcı adı veya şifre")

    settings = get_settings()
    token = create_jwt_token({
        "sub": admin.username,
        "role": "admin",
    })

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiration_minutes * 60,
    )


# ============================================
# Dashboard
# ============================================

@router.get("/clients")
async def list_clients(_auth: dict = Depends(verify_jwt_token)):
    """Sistemdeki tüm müşterileri döndürür."""
    clients = await repo.get_all_clients()
    return {
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "api_key": c.api_key,
                "tier": c.tier,
                "billing_day": c.billing_day,
                "is_overdue": c.is_overdue,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in clients
        ]
    }


@router.post("/clients")
async def create_client(req: ClientCreateRequest, _auth: dict = Depends(verify_jwt_token)):
    """Yeni müşteri oluşturur."""
    client = await repo.create_client(req.name, req.tier, req.billing_day)
    return {"message": "Müşteri oluşturuldu", "id": client.id, "api_key": client.api_key}


@router.put("/clients/{client_id}")
async def update_client(client_id: int, req: ClientUpdateRequest, _auth: dict = Depends(verify_jwt_token)):
    """Müşteri bilgilerini günceller."""
    client = await repo.update_client(
        client_id, req.name, req.tier, req.billing_day, req.is_overdue, req.is_active
    )
    if not client:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    return {"message": "Müşteri güncellendi"}


@router.post("/clients/{client_id}/api_key")
async def regenerate_api_key(client_id: int, _auth: dict = Depends(verify_jwt_token)):
    """Müşterinin API anahtarını sıfırlar."""
    client = await repo.regenerate_client_api_key(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    return {"message": "API Key yenilendi", "api_key": client.api_key}


@router.delete("/clients/{client_id}")
async def delete_client(client_id: int, _auth: dict = Depends(verify_jwt_token)):
    """Müşteriyi siler."""
    success = await repo.delete_client(client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
    return {"message": "Müşteri silindi"}


@router.get("/dashboard")
async def get_dashboard(client_id: int | None = None, _auth: dict = Depends(verify_jwt_token)):
    """Dashboard özet istatistikleri ve grafik verileri."""
    db_stats = await repo.get_dashboard_stats(client_id)
    chart_data = await repo.get_chart_data(client_id)
    pipeline_stats = get_pipeline_stats()

    return {
        **db_stats,
        "chart_data": chart_data,
        "pipeline": pipeline_stats,
    }


# ============================================
# Player Management
# ============================================

@router.get("/players")
async def list_players(
    status: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "risk_score",
    _auth: dict = Depends(verify_jwt_token),
):
    """Oyuncu listesi (filtrelenebilir, sıralanabilir, sayfalanabilir)."""
    players, total = await repo.get_players(
        status=status, client_id=client_id, limit=limit, offset=offset, sort_by=sort_by
    )

    return {
        "players": [
            {
                "player_id": p.player_id,
                "status": p.status,
                "risk_level": p.risk_level,
                "risk_score": p.risk_score,
                "total_events": p.total_events,
                "flagged_count": p.flagged_count,
                "last_seen": p.last_seen.isoformat() if p.last_seen else None,
            }
            for p in players
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/players/{player_id}")
async def get_player(player_id: str, client_id: int | None = None, _auth: dict = Depends(verify_jwt_token)):
    """Oyuncu detay bilgisi."""
    # Note: the current get_player_detail takes client_id and player_id. 
    # If client_id is not given, we can't reliably get the player if IDs overlap across clients.
    # But for admin, let's assume they provide client_id.
    if client_id is None:
        raise HTTPException(status_code=400, detail="client_id is required to fetch player details")
        
    player = await repo.get_player_detail(client_id, player_id)

    if player is None:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    # Redis'ten ek veriler
    redis = await get_redis()
    ml_result = await redis.hgetall(f"vektia:player:{player_id}:ml_result")
    is_suspicious = await redis.sismember("vektia:flagged:suspicious", player_id)
    is_confirmed = await redis.sismember("vektia:flagged:confirmed", player_id)

    return {
        "player_id": player.player_id,
        "server_id": player.server_id,
        "status": player.status,
        "risk_level": player.risk_level,
        "risk_score": player.risk_score,
        "std_deviation": player.std_deviation,
        "total_events": player.total_events,
        "flagged_count": player.flagged_count,
        "ban_reason": player.ban_reason,
        "banned_by": player.banned_by,
        "first_seen": player.first_seen.isoformat() if player.first_seen else None,
        "last_seen": player.last_seen.isoformat() if player.last_seen else None,
        "banned_at": player.banned_at.isoformat() if player.banned_at else None,
        "ml_result": ml_result if ml_result else None,
        "in_suspicious_pool": is_suspicious,
        "in_confirmed_pool": is_confirmed,
    }


@router.post("/players/{player_id}/ban")
async def ban_player(
    player_id: str,
    request: BanRequest,
    client_id: int,
    auth: dict = Depends(verify_jwt_token),
):
    """Oyuncuyu banla (admin onaylı)."""
    player = await repo.update_player_status(
        client_id=client_id,
        player_id=player_id,
        status="banned",
        ban_reason=request.reason,
        banned_by=auth.get("sub", "admin"),
    )

    if player is None:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    # Redis'ten temizle
    redis = await get_redis()
    await redis.srem("vektia:flagged:suspicious", player_id)
    await redis.srem("vektia:flagged:confirmed", player_id)
    await redis.sadd("vektia:banned", player_id)

    logger.info(f"Oyuncu banlandı: {player_id} (neden: {request.reason}, admin: {auth.get('sub')})")

    return {"message": f"Oyuncu {player_id} banlandı", "status": "banned"}


@router.post("/players/{player_id}/whitelist")
async def whitelist_player(
    player_id: str,
    request: WhitelistRequest,
    client_id: int,
    auth: dict = Depends(verify_jwt_token),
):
    """Oyuncuyu beyaz listeye al (false positive düzeltme)."""
    player = await repo.update_player_status(
        client_id=client_id,
        player_id=player_id,
        status="whitelisted",
        risk_level="clean",
        risk_score=0.0,
    )

    if player is None:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")

    # Redis'ten temizle
    redis = await get_redis()
    await redis.srem("vektia:flagged:suspicious", player_id)
    await redis.srem("vektia:flagged:confirmed", player_id)
    await redis.sadd("vektia:whitelisted", player_id)

    return {"message": f"Oyuncu {player_id} beyaz listeye alındı", "status": "whitelisted"}


# ============================================
# Alerts
# ============================================

@router.get("/alerts")
async def get_alerts(
    client_id: int | None = None,
    limit: int = 50,
    _auth: dict = Depends(verify_jwt_token),
):
    """Son uyarıları listele."""
    redis = await get_redis()
    
    # We should use PostgreSQL for all alerts across clients to be robust.
    # Let's read from DetectionLog instead of Redis to support cross-client queries.
    logs = await repo.get_recent_detections(limit, client_id)
    
    alerts = []
    for log in logs:
        alerts.append({
            "player_id": log.player_id,
            "layer": log.layer,
            "risk_level": log.risk_level,
            "score": log.risk_score,
            "client_id": log.client_id,
            "detected_at": log.detected_at.isoformat() if log.detected_at else None
        })

    return {"alerts": alerts, "count": len(alerts)}
    # This method of parsing JSON alerts is removed.


# ============================================
# System Stats
# ============================================

@router.get("/stats")
async def get_system_stats(_auth: dict = Depends(verify_jwt_token)):
    """Sistem performans metrikleri."""
    redis = await get_redis()

    # Redis bellek kullanımı
    info = await redis.info("memory")
    memory_used = info.get("used_memory_human", "N/A")

    # Kuyruk boyutları
    ml_queue_size = await redis.llen("vektia:ml_queue")
    suspicious_count = await redis.scard("vektia:flagged:suspicious")
    confirmed_count = await redis.scard("vektia:flagged:confirmed")

    return {
        "redis_memory": memory_used,
        "ml_queue_size": ml_queue_size,
        "suspicious_pool_size": suspicious_count,
        "confirmed_pool_size": confirmed_count,
        "pipeline": get_pipeline_stats(),
    }
