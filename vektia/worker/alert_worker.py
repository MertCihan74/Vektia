"""
Vektia Alert Worker

Onaylanmış bot tespitlerini yönetir:
- Admin paneline bildirim gönderme
- Webhook ile oyun sunucusuna ban emri gönderme (opsiyonel)
- Ban kayıtlarını kalıcı veritabanına yazma
"""

import asyncio
import json

import httpx

from vektia.db.redis_client import get_redis
from vektia.db import repositories as repo
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


async def send_webhook_notification(
    webhook_url: str,
    player_id: str,
    risk_level: str,
    anomaly_score: float,
) -> bool:
    """
    Oyun sunucusuna webhook bildirimi gönderir.
    
    Args:
        webhook_url: Hedef URL
        player_id: İşaretlenen oyuncu
        risk_level: Risk seviyesi
        anomaly_score: Anomali skoru
        
    Returns:
        Başarı durumu
    """
    settings = get_settings()

    payload = {
        "event": "player_flagged",
        "player_id": player_id,
        "risk_level": risk_level,
        "anomaly_score": anomaly_score,
        "action": "ban" if settings.auto_ban_enabled else "flag",
        "source": "vektia",
    }

    for attempt in range(settings.webhook_max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=settings.webhook_timeout_seconds,
                    headers={"X-Vektia-Signature": "v1"},  # TODO: HMAC imza
                )

                if response.status_code == 200:
                    logger.info(f"Webhook başarılı: {player_id} → {webhook_url}")
                    return True
                else:
                    logger.warning(
                        f"Webhook yanıt hatası ({response.status_code}): "
                        f"{player_id} → {webhook_url}"
                    )
        except httpx.TimeoutException:
            logger.warning(
                f"Webhook timeout (deneme {attempt + 1}/{settings.webhook_max_retries}): "
                f"{webhook_url}"
            )
        except Exception as e:
            logger.error(f"Webhook hatası: {e}")

    logger.error(f"Webhook tüm denemelerde başarısız: {webhook_url}")
    return False


async def process_confirmed_bots() -> int:
    """
    Onaylanmış bot listesini işler ve webhook bildirimlerini gönderir.
    
    Returns:
        İşlenen bot sayısı
    """
    redis = await get_redis()

    # Kayıtlı webhook URL'lerini al
    webhook_urls = await redis.smembers("vektia:webhooks")

    # Onaylanmış botları al (Tüm müşteriler için tara)
    keys = await redis.keys("vektia:client:*:flagged:confirmed")
    processed = 0

    for key in keys:
        client_id = key.split(":")[2]
        confirmed_bots = await redis.smembers(key)

        for player_id in confirmed_bots:
            # Daha önce bildirildiyse atla
            if await redis.sismember(f"vektia:client:{client_id}:flagged:notified", player_id):
                continue
                
            # Bot ML sonucunu al
            ml_result = await redis.hgetall(f"vektia:client:{client_id}:player:{player_id}:ml_result")

            if not ml_result:
                continue

            anomaly_score = float(ml_result.get("anomaly_score", 0))
            risk_level = ml_result.get("risk_level", "confirmed")

            # Müşteri ayarlarını kontrol et ve Otomatik Ban uygula
            client_settings = await repo.get_client_settings(int(client_id))
            if client_settings and client_settings.get("auto_ban_enabled"):
                should_ban = False
                
                if risk_level in ["high", "confirmed"] and client_settings.get("auto_ban_high_risk"):
                    should_ban = True
                elif risk_level == "suspicious" and client_settings.get("auto_ban_suspicious"):
                    should_ban = True
                    
                if should_ban:
                    logger.info(f"Auto-Ban tetiklendi: client={client_id} player={player_id} risk={risk_level}")
                    await repo.update_player_status(
                        client_id=int(client_id),
                        player_id=player_id,
                        status="banned",
                        ban_reason=f"Otomatik Engelleme (Risk: {risk_level})",
                        banned_by="auto_ban_system"
                    )

            # TODO: Get specific webhook for client_id from Postgres
            # For now, just print or mock
            logger.info(f"Alert: client={client_id} player={player_id} risk={risk_level}")

            # İşlendi olarak işaretle
            await redis.sadd(f"vektia:client:{client_id}:flagged:notified", player_id)
            processed += 1

    # Aynı işlemi Şüpheli (Suspicious) olanlar için de tarayalım (kuyrukta bekleyenler)
    keys_suspicious = await redis.keys("vektia:client:*:flagged:suspicious")
    for key in keys_suspicious:
        client_id = key.split(":")[2]
        suspicious_bots = await redis.smembers(key)
        
        client_settings = await repo.get_client_settings(int(client_id))
        if client_settings and client_settings.get("auto_ban_enabled") and client_settings.get("auto_ban_suspicious"):
            for player_id in suspicious_bots:
                logger.info(f"Auto-Ban (Suspicious) tetiklendi: client={client_id} player={player_id}")
                await repo.update_player_status(
                    client_id=int(client_id),
                    player_id=player_id,
                    status="banned",
                    ban_reason="Otomatik Engelleme (Risk: suspicious)",
                    banned_by="auto_ban_system"
                )
                await redis.sadd(f"vektia:client:{client_id}:flagged:notified", player_id)
                await redis.srem(key, player_id)
                processed += 1

    return processed


async def alert_worker_loop() -> None:
    """Alert worker ana döngüsü."""
    logger.info("Alert Worker başlatıldı")

    while True:
        try:
            processed = await process_confirmed_bots()
            if processed > 0:
                logger.info(f"Alert batch: {processed} bot bildirildi")
        except Exception as e:
            logger.error(f"Alert worker hatası: {e}")

        await asyncio.sleep(60)  # Her dakika kontrol et
