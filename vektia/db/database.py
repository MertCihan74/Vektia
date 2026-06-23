"""
Vektia Database — SQLAlchemy Async Models & Engine

Kalıcı depolama: Ban kayıtları, admin kullanıcıları, sunucu kayıtları
ve webhook konfigürasyonları SQLite (MVP) / PostgreSQL (production) ile tutulur.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================
# SQLAlchemy Base
# ============================================

class Base(DeclarativeBase):
    """Tüm ORM modelleri için temel sınıf."""
    pass


# ============================================
# ORM Models
# ============================================

class AdminUser(Base):
    """Süper Admin kullanıcı tablosu."""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)


class Client(Base):
    """Müşteri (Oyun Stüdyosu) tablosu."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    email = Column(String(128), unique=True, nullable=True, index=True)
    api_key = Column(String(128), unique=True, nullable=False, index=True)
    tier = Column(String(20), default="premium")  # "free" or "premium"
    billing_day = Column(Integer, default=1)      # 1-31
    is_overdue = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Yeni Billing & Lemon Squeezy Kolonları
    ls_customer_id = Column(String(128), nullable=True, index=True)
    subscription_id = Column(String(128), nullable=True, index=True)
    subscription_status = Column(String(50), default="inactive") # active, past_due, canceled, inactive
    subscription_end_date = Column(DateTime(timezone=True), nullable=True)

    # Otomatik Engelleme (Auto-Ban) Ayarları
    auto_ban_enabled = Column(Boolean, default=False)
    auto_ban_high_risk = Column(Boolean, default=False)
    auto_ban_suspicious = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class VerificationOTP(Base):
    """E-posta doğrulama için OTP kodlarını tutan tablo."""
    __tablename__ = "verification_otps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(128), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PlayerRecord(Base):
    """Oyuncu ban/flag kayıt tablosu."""
    __tablename__ = "player_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, index=True, nullable=False)
    player_id = Column(String(128), nullable=False, index=True)
    server_id = Column(String(64), nullable=True)
    status = Column(String(20), default="active")  # active, flagged, banned, whitelisted
    risk_level = Column(String(20), default="clean")
    risk_score = Column(Float, default=0.0)
    std_deviation = Column(Float, default=0.0)
    total_events = Column(Integer, default=0)
    flagged_count = Column(Integer, default=0)
    ban_reason = Column(Text, nullable=True)
    banned_by = Column(String(64), nullable=True)  # admin username veya "auto"
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    banned_at = Column(DateTime(timezone=True), nullable=True)


class WebhookConfig(Base):
    """Webhook konfigürasyon tablosu."""
    __tablename__ = "webhook_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, index=True, nullable=False)
    server_id = Column(String(64), nullable=False)
    url = Column(String(512), nullable=False)
    secret = Column(String(256), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DetectionLog(Base):
    """Tespit log tablosu — analitik ve raporlama için."""
    __tablename__ = "detection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, index=True, nullable=False)
    player_id = Column(String(128), nullable=False, index=True)
    layer = Column(Integer, nullable=False)
    risk_level = Column(String(20), nullable=False)
    risk_score = Column(Float, nullable=False)
    std_deviation = Column(Float, default=0.0)
    details = Column(Text, nullable=True)  # JSON string
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ============================================
# Engine & Session Factory
# ============================================

_engine = None
_session_factory = None


async def init_database() -> None:
    """Veritabanı engine'ini başlatır ve tabloları oluşturur."""
    global _engine, _session_factory

    settings = get_settings()

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Tabloları oluştur (yoksa)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(f"Veritabanı başlatıldı: {settings.database_url}")

    # Varsayılan admin kullanıcısını ve test müşterilerini oluştur
    await _create_default_admin()
    await _create_test_clients()


async def _create_default_admin() -> None:
    """İlk çalıştırmada varsayılan admin kullanıcısını oluşturur."""
    from vektia.utils.security import hash_password

    settings = get_settings()

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(AdminUser).where(AdminUser.username == settings.admin_username)
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            admin = AdminUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
            session.add(admin)
            await session.commit()
            logger.info(f"Varsayılan admin oluşturuldu: {settings.admin_username}")


async def _create_test_clients() -> None:
    """Test için 2 adet varsayılan müşteri oluşturur."""
    async with get_session() as session:
        from sqlalchemy import select
        
        result = await session.execute(select(Client))
        clients = result.scalars().all()
        
        if not clients:
            client_a = Client(name="Studio A (Premium)", api_key="test_api_key_A", tier="premium")
            client_b = Client(name="Studio B (Free-Tier)", api_key="test_api_key_B", tier="free")
            session.add_all([client_a, client_b])
            await session.commit()
            logger.info("Test müşterileri oluşturuldu: test_api_key_A (premium), test_api_key_B (free)")


def get_session() -> AsyncSession:
    """Yeni veritabanı oturumu döndürür."""
    if _session_factory is None:
        raise RuntimeError("Veritabanı henüz başlatılmadı. init_database() çağırın.")
    return _session_factory()


async def close_database() -> None:
    """Veritabanı bağlantısını kapatır."""
    global _engine, _session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Veritabanı bağlantısı kapatıldı")
