"""
Vektia Repositories — CRUD Operasyonları

Veritabanı işlemlerini soyutlayan repository katmanı.
API endpoint'leri doğrudan SQL sorgusu yazmaz, bu modülü kullanır.
"""

from datetime import datetime, timezone, timedelta
import secrets

from sqlalchemy import select, func, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from vektia.db.database import (
    get_session,
    AdminUser,
    Client,
    PlayerRecord,
    WebhookConfig,
    DetectionLog,
    VerificationOTP,
)
from vektia.utils.security import verify_password, hash_password
from vektia.core.metrics import false_positive_rate as _fp_rate
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================
# Admin User Repository
# ============================================

async def authenticate_admin(username: str, password: str) -> AdminUser | None:
    """Admin kullanıcısını doğrular."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(
                AdminUser.username == username,
                AdminUser.is_active == True,
            )
        )
        admin = result.scalar_one_or_none()

        if admin and verify_password(password, admin.password_hash):
            # Son giriş zamanını güncelle
            admin.last_login = datetime.now(timezone.utc)
            await session.commit()
            return admin
        return None


# ============================================
# Client Repository
# ============================================

async def get_client_by_api_key(api_key: str) -> Client | None:
    """API Key ile müşteriyi bulur."""
    async with get_session() as session:
        result = await session.execute(
            select(Client).where(Client.api_key == api_key, Client.is_active == True)
        )
        return result.scalar_one_or_none()

async def get_client_by_id(client_id: int) -> Client | None:
    """ID ile müşteriyi bulur."""
    async with get_session() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


async def get_all_clients() -> list[Client]:
    """Sistemdeki tüm müşterileri döndürür."""
    async with get_session() as session:
        result = await session.execute(select(Client).order_by(desc(Client.created_at)))
        return list(result.scalars().all())


async def toggle_client_status(client_id: int) -> Client | None:
    """Müşterinin aktiflik durumunu tersine çevirir."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.is_active = not client.is_active
            await session.commit()
            await session.refresh(client)
        return client


async def check_domain_free_tier(domain: str) -> bool:
    """Belirtilen domain'in daha önce free tier alıp almadığını kontrol eder."""
    async with get_session() as session:
        # PostgreSQL ILIKE for case-insensitive match on domain
        result = await session.execute(
            select(Client).where(Client.email.ilike(f"%@{domain}"), Client.tier == "free")
        )
        return result.scalar_one_or_none() is not None


async def create_client(name: str, email: str | None = None, tier: str = "premium", billing_day: int = 1) -> Client:
    """Yeni müşteri (Client) oluşturur ve API key üretir."""
    api_key = f"vkt_{secrets.token_urlsafe(24)}"
    
    subscription_end_date = None
    if tier == "free":
        subscription_end_date = datetime.now(timezone.utc) + timedelta(days=7)
        
    client = Client(
        name=name, 
        email=email, 
        api_key=api_key, 
        tier=tier, 
        billing_day=billing_day,
        subscription_end_date=subscription_end_date
    )
    
    async with get_session() as session:
        session.add(client)
        await session.commit()
        await session.refresh(client)
        return client


async def update_client(client_id: int, name: str, tier: str, billing_day: int, is_overdue: bool, is_active: bool) -> Client | None:
    """Müşteri bilgilerini günceller."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.name = name
            client.tier = tier
            client.billing_day = billing_day
            client.is_overdue = is_overdue
            client.is_active = is_active
            await session.commit()
            await session.refresh(client)
        return client


async def get_client_settings(client_id: int) -> dict | None:
    """Müşterinin ayarlarını döndürür."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            return None
        return {
            "auto_ban_enabled": client.auto_ban_enabled,
            "auto_ban_high_risk": client.auto_ban_high_risk,
            "auto_ban_suspicious": client.auto_ban_suspicious,
        }


async def update_client_settings(client_id: int, auto_ban_enabled: bool, auto_ban_high_risk: bool, auto_ban_suspicious: bool) -> bool:
    """Müşteri ayarlarını günceller."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.auto_ban_enabled = auto_ban_enabled
            client.auto_ban_high_risk = auto_ban_high_risk
            client.auto_ban_suspicious = auto_ban_suspicious
            await session.commit()
            return True
        return False

async def regenerate_client_api_key(client_id: int) -> Client | None:
    """Müşterinin API Key'ini yeniler."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.api_key = f"vkt_{secrets.token_urlsafe(24)}"
            await session.commit()
            await session.refresh(client)
        return client


async def process_expired_subscriptions():
    """Bitiş süresi dolmuş abonelikleri işler."""
    async with get_session() as session:
        now = datetime.now(timezone.utc)
        
        # 1. Premium olup süresi biten ve iptal edilmiş (canceled) olanlar -> Free'ye düşür (7 gün ver)
        result_premium = await session.execute(
            select(Client).where(
                Client.tier == "premium",
                Client.subscription_status == "canceled",
                Client.subscription_end_date <= now
            )
        )
        expired_premiums = result_premium.scalars().all()
        for client in expired_premiums:
            client.tier = "free"
            client.subscription_end_date = now + timedelta(days=7)
            logger.info(f"Client {client.id} ({client.name}) Premium süresi doldu, Free'ye düşürüldü.")
            
        # 2. Free olup süresi bitenler -> is_active = False yap (Hesabı pasife al)
        result_free = await session.execute(
            select(Client).where(
                Client.tier == "free",
                Client.subscription_end_date <= now,
                Client.is_active == True
            )
        )
        expired_frees = result_free.scalars().all()
        for client in expired_frees:
            client.is_active = False
            logger.info(f"Client {client.id} ({client.name}) Free süresi doldu, hesabı pasife alındı.")
            
        if expired_premiums or expired_frees:
            await session.commit()


async def delete_client(client_id: int) -> bool:
    """Müşteriyi veritabanından siler."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            await session.delete(client)
            await session.commit()
            return True
        return False


# ============================================
# OTP & Billing Repository
# ============================================

async def create_verification_otp(email: str) -> str:
    """Belirtilen e-posta için 6 haneli OTP kodu üretir ve veritabanına kaydeder."""
    import random
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    otp_record = VerificationOTP(email=email, otp_code=otp_code, expires_at=expires_at)
    async with get_session() as session:
        session.add(otp_record)
        await session.commit()
        return otp_code

async def verify_otp(email: str, otp_code: str) -> bool:
    """E-posta ve OTP eşleşmesini ve süresini kontrol eder."""
    async with get_session() as session:
        # En son üretilen geçerli kodu bul
        result = await session.execute(
            select(VerificationOTP).where(
                VerificationOTP.email == email,
                VerificationOTP.otp_code == otp_code,
                VerificationOTP.expires_at > datetime.now(timezone.utc)
            ).order_by(desc(VerificationOTP.created_at)).limit(1)
        )
        record = result.scalar_one_or_none()
        return record is not None

async def update_client_subscription(client_id: int, ls_customer_id: str, subscription_id: str, status: str, end_date: datetime) -> Client | None:
    """Müşterinin Lemon Squeezy abonelik bilgilerini günceller."""
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.ls_customer_id = ls_customer_id
            client.subscription_id = subscription_id
            client.subscription_status = status
            client.subscription_end_date = end_date
            # Abonelik aktifse hesabı da aktif et
            if status == "active":
                client.is_active = True
                client.tier = "premium"
            await session.commit()
            await session.refresh(client)
        return client

async def get_client_by_ls_customer_id(ls_customer_id: str) -> Client | None:
    """Lemon Squeezy Müşteri ID'sine göre müşteriyi bulur."""
    async with get_session() as session:
        result = await session.execute(
            select(Client).where(Client.ls_customer_id == ls_customer_id)
        )
        return result.scalar_one_or_none()


# ============================================
# Player Record Repository
# ============================================

async def get_or_create_player(client_id: int, player_id: str, server_id: str | None = None) -> PlayerRecord:
    """Oyuncu kaydını döndürür, yoksa oluşturur."""
    async with get_session() as session:
        result = await session.execute(
            select(PlayerRecord).where(
                PlayerRecord.client_id == client_id,
                PlayerRecord.player_id == player_id
            )
        )
        player = result.scalars().first()

        if player is None:
            player = PlayerRecord(client_id=client_id, player_id=player_id, server_id=server_id)
            session.add(player)
            await session.commit()
            await session.refresh(player)

        return player


async def update_player_status(
    client_id: int,
    player_id: str,
    status: str,
    risk_level: str | None = None,
    risk_score: float | None = None,
    ban_reason: str | None = None,
    banned_by: str | None = None,
) -> PlayerRecord | None:
    """Oyuncu durumunu günceller."""
    async with get_session() as session:
        result = await session.execute(
            select(PlayerRecord).where(
                PlayerRecord.client_id == client_id,
                PlayerRecord.player_id == player_id
            )
        )
        player = result.scalars().first()

        if player is None:
            return None

        player.status = status
        if risk_level:
            player.risk_level = risk_level
        if risk_score is not None:
            player.risk_score = risk_score
        if ban_reason:
            player.ban_reason = ban_reason
        if banned_by:
            player.banned_by = banned_by
        if status == "banned":
            player.banned_at = datetime.now(timezone.utc)

        player.last_seen = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(player)
        return player


async def get_players(
    status: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "risk_score",
) -> tuple[list[PlayerRecord], int]:
    """Oyuncu listesini döndürür (filtrelenebilir, sıralanabilir)."""
    async with get_session() as session:
        query = select(PlayerRecord)
        count_query = select(func.count()).select_from(PlayerRecord)

        if status:
            query = query.where(PlayerRecord.status == status)
            count_query = count_query.where(PlayerRecord.status == status)
            
        if client_id is not None:
            query = query.where(PlayerRecord.client_id == client_id)
            count_query = count_query.where(PlayerRecord.client_id == client_id)

        # Sıralama
        sort_column = getattr(PlayerRecord, sort_by, PlayerRecord.risk_score)
        query = query.order_by(desc(sort_column))

        # Sayfalama
        query = query.limit(limit).offset(offset)

        result = await session.execute(query)
        players = list(result.scalars().all())

        count_result = await session.execute(count_query)
        total = count_result.scalar()

        return players, total


async def get_player_detail(client_id: int, player_id: str) -> PlayerRecord | None:
    """Tek bir oyuncunun detaylı kaydını döndürür."""
    async with get_session() as session:
        result = await session.execute(
            select(PlayerRecord).where(
                PlayerRecord.client_id == client_id,
                PlayerRecord.player_id == player_id
            )
        )
        return result.scalar_one_or_none()


async def increment_player_events(client_id: int, player_id: str) -> None:
    """Oyuncunun toplam olay sayısını artırır (tekil)."""
    async with get_session() as session:
        await session.execute(
            update(PlayerRecord)
            .where(
                PlayerRecord.client_id == client_id,
                PlayerRecord.player_id == player_id
            )
            .values(
                total_events=PlayerRecord.total_events + 1,
                last_seen=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def add_player_events(client_id: int, player_id: str, count: int) -> None:
    """
    Oyuncunun toplam olay sayısını TOPLU artırır (event_buffer flush'ı için).
    Her olayda DB'ye yazmak yerine Redis'te biriken sayaç periyodik olarak buradan uygulanır.
    """
    if count <= 0:
        return
    async with get_session() as session:
        await session.execute(
            update(PlayerRecord)
            .where(
                PlayerRecord.client_id == client_id,
                PlayerRecord.player_id == player_id
            )
            .values(
                total_events=PlayerRecord.total_events + count,
                last_seen=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def get_whitelisted_player_ids() -> list[str]:
    """Whitelisted oyuncuların player_id'leri (başlangıçta Redis set'ine yüklemek için)."""
    async with get_session() as session:
        result = await session.execute(
            select(PlayerRecord.player_id).where(PlayerRecord.status == "whitelisted")
        )
        return [row[0] for row in result.all()]


# ============================================
# Dashboard Statistics
# ============================================

async def get_dashboard_stats(client_id: int | None = None) -> dict:
    """Dashboard istatistiklerini döndürür."""
    async with get_session() as session:
        q_total = select(func.count(PlayerRecord.player_id.distinct()))
        q_active = select(func.count(PlayerRecord.player_id.distinct())).where(PlayerRecord.status == "active")
        q_flagged = select(func.count(PlayerRecord.player_id.distinct())).where(PlayerRecord.status == "flagged")
        q_banned = select(func.count(PlayerRecord.player_id.distinct())).where(PlayerRecord.status == "banned")
        q_whitelisted = select(func.count(PlayerRecord.player_id.distinct())).where(PlayerRecord.status == "whitelisted")

        q_events = select(func.sum(PlayerRecord.total_events))

        if client_id is not None:
            q_total = q_total.where(PlayerRecord.client_id == client_id)
            q_active = q_active.where(PlayerRecord.client_id == client_id)
            q_flagged = q_flagged.where(PlayerRecord.client_id == client_id)
            q_banned = q_banned.where(PlayerRecord.client_id == client_id)
            q_whitelisted = q_whitelisted.where(PlayerRecord.client_id == client_id)
            q_events = q_events.where(PlayerRecord.client_id == client_id)

        total = await session.execute(q_total)
        active = await session.execute(q_active)
        flagged = await session.execute(q_flagged)
        banned = await session.execute(q_banned)
        whitelisted = await session.execute(q_whitelisted)
        events = await session.execute(q_events)

        flagged_n = flagged.scalar() or 0
        banned_n = banned.scalar() or 0
        whitelisted_n = whitelisted.scalar() or 0

        # Faz 4 — Yanlış-pozitif oranı telemetrisi (saf hesaplama metrics.py'de).
        # Admin bir oyuncuyu whitelist'e aldıysa, sistemin işaretlemesi yanlıştı
        # (false positive) demektir.
        false_positive_rate = _fp_rate(flagged_n, banned_n, whitelisted_n)

        return {
            "total_players": total.scalar() or 0,
            "active_players": active.scalar() or 0,
            "flagged_players": flagged_n,
            "banned_players": banned_n,
            "whitelisted_players": whitelisted_n,
            "total_events": events.scalar() or 0,
            "false_positive_rate": false_positive_rate,
        }


async def get_chart_data(client_id: int | None = None) -> dict:
    """Dashboard grafikleri için canlı verileri döndürür."""
    async with get_session() as session:
        # 1. Risk Dağılımı (PlayerRecord.risk_level bazlı)
        q_risk = select(PlayerRecord.risk_level, func.count(PlayerRecord.player_id)).group_by(PlayerRecord.risk_level)
        if client_id is not None:
            q_risk = q_risk.where(PlayerRecord.client_id == client_id)
            
        risk_counts_result = await session.execute(q_risk)
        risk_distribution = {
            "clean": 0, "low": 0, "suspicious": 0, "high": 0, "confirmed": 0
        }
        for level, count in risk_counts_result.all():
            if level in risk_distribution:
                risk_distribution[level] = count
        
        # 2. Zaman Serisi (Son 1 Saat, Dakika Bazlı)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        q_logs = select(DetectionLog).where(DetectionLog.detected_at >= one_hour_ago)
        if client_id is not None:
            q_logs = q_logs.where(DetectionLog.client_id == client_id)
            
        logs_result = await session.execute(q_logs)
        logs = list(logs_result.scalars().all())
        
        now = datetime.now(timezone.utc)
        # 60 dakikalık etiketler (Örn: 10:45)
        minutes_labels = [ (now - timedelta(minutes=i)).strftime('%H:%M') for i in range(59, -1, -1) ]
        
        timeline_data = {
            "labels": minutes_labels,
            "clean": [0] * 60, # Simülasyonda temiz loglanmıyor ama chart için 0 koyalım
            "suspicious": [0] * 60,
            "flagged": [0] * 60,
        }
        
        for log in logs:
            if not log.detected_at: continue
            # timezone-aware datetime hesaplama
            log_time = log.detected_at
            if log_time.tzinfo is None:
                log_time = log_time.replace(tzinfo=timezone.utc)
                
            diff_minutes = (now - log_time).total_seconds() / 60
            if 0 <= diff_minutes < 60:
                idx = 59 - int(diff_minutes)
                if log.risk_level in ("high", "confirmed"):
                    timeline_data["flagged"][idx] += 1
                elif log.risk_level in ("suspicious", "low"):
                    timeline_data["suspicious"][idx] += 1
                    
        return {
            "risk_distribution": risk_distribution,
            "timeline": timeline_data
        }



# ============================================
# Detection Log Repository
# ============================================

async def log_detection(
    client_id: int,
    player_id: str,
    layer: int,
    risk_level: str,
    risk_score: float,
    std_deviation: float = 0.0,
    details: str | None = None,
) -> None:
    """Tespit logunu veritabanına kaydeder."""
    async with get_session() as session:
        log = DetectionLog(
            client_id=client_id,
            player_id=player_id,
            layer=layer,
            risk_level=risk_level,
            risk_score=risk_score,
            std_deviation=std_deviation,
            details=details,
        )
        session.add(log)
        await session.commit()


async def get_recent_detections(limit: int = 50, client_id: int | None = None) -> list[DetectionLog]:
    """Son tespitleri döndürür."""
    async with get_session() as session:
        query = select(DetectionLog).order_by(desc(DetectionLog.detected_at)).limit(limit)
        if client_id is not None:
            query = query.where(DetectionLog.client_id == client_id)
            
        result = await session.execute(query)
        return list(result.scalars().all())


# ============================================
# Webhook Repository
# ============================================

async def register_webhook(server_id: str, url: str, secret: str | None = None) -> WebhookConfig:
    """Yeni webhook kaydeder."""
    async with get_session() as session:
        webhook = WebhookConfig(server_id=server_id, url=url, secret=secret)
        session.add(webhook)
        await session.commit()
        await session.refresh(webhook)
        return webhook


async def get_active_webhooks() -> list[WebhookConfig]:
    """Aktif webhook'ları döndürür."""
    async with get_session() as session:
        result = await session.execute(
            select(WebhookConfig).where(WebhookConfig.is_active == True)
        )
        return list(result.scalars().all())
