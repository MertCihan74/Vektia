"""
Vektia Configuration Module

Pydantic Settings ile ortam değişkenlerinden tüm yapılandırmayı yükler.
Tüm ayarlar VEKTIA_ prefix'i ile .env dosyasından okunur.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Ana uygulama ayarları — .env dosyasından otomatik yüklenir."""

    # --- Application ---
    app_name: str = Field(default="Vektia", alias="VEKTIA_APP_NAME")
    version: str = Field(default="0.1.0", alias="VEKTIA_VERSION")
    debug: bool = Field(default=False, alias="VEKTIA_DEBUG")
    host: str = Field(default="0.0.0.0", alias="VEKTIA_HOST")
    port: int = Field(default=8000, alias="VEKTIA_PORT")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="VEKTIA_REDIS_URL")
    redis_max_connections: int = Field(default=50, alias="VEKTIA_REDIS_MAX_CONNECTIONS")

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./vektia.db",
        alias="VEKTIA_DATABASE_URL",
    )

    # --- JWT Auth ---
    jwt_secret_key: str = Field(
        default="change-me-in-production",
        alias="VEKTIA_JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="VEKTIA_JWT_ALGORITHM")
    jwt_expiration_minutes: int = Field(default=1440, alias="VEKTIA_JWT_EXPIRATION_MINUTES")

    # --- Admin ---
    admin_username: str = Field(default="admin", alias="VEKTIA_ADMIN_USERNAME")
    admin_password: str = Field(default="admin123", alias="VEKTIA_ADMIN_PASSWORD")

    # --- API Key ---
    master_api_key: str = Field(
        default="vektia-dev-key",
        alias="VEKTIA_MASTER_API_KEY",
    )

    # --- Detection Thresholds ---
    # NOT: Tüm zaman eşikleri MİLİSANİYE cinsindendir (kanonik birim,
    # bkz. TELEMETRY_DATA_FORMAT.md). Önceki saniye-cinsi değerler ms veriyle
    # hiç tetiklenmiyordu; ms'e taşındı.
    max_window: int = Field(default=20, alias="VEKTIA_MAX_WINDOW")
    bot_threshold: float = Field(default=3.0, alias="VEKTIA_BOT_THRESHOLD")           # ms: std bu değerin altındaysa bot benzeri
    suspicious_threshold: float = Field(default=15.0, alias="VEKTIA_SUSPICIOUS_THRESHOLD")  # ms: std bu değerin altındaysa şüpheli
    player_ttl_seconds: int = Field(default=300, alias="VEKTIA_PLAYER_TTL_SECONDS")
    ml_batch_interval_seconds: int = Field(default=30, alias="VEKTIA_ML_BATCH_INTERVAL_SECONDS")

    # --- Temporal Evidence (Yanlış Pozitif Azaltma) ---
    # Tek bir pencere asla kesin karar üretmez. Şüpheli pencereler bir "kanıt
    # skoru"nda birikir; temiz pencereler bu skoru söndürür (decay). Kesin karar
    # ancak kanıt confirm eşiğini aşınca verilir.
    temporal_enabled: bool = Field(default=True, alias="VEKTIA_TEMPORAL_ENABLED")
    temporal_decay_factor: float = Field(default=0.6, alias="VEKTIA_TEMPORAL_DECAY_FACTOR")
    temporal_high_increment: float = Field(default=1.0, alias="VEKTIA_TEMPORAL_HIGH_INCREMENT")
    temporal_suspicious_increment: float = Field(default=0.4, alias="VEKTIA_TEMPORAL_SUSPICIOUS_INCREMENT")
    temporal_suspect_threshold: float = Field(default=0.8, alias="VEKTIA_TEMPORAL_SUSPECT_THRESHOLD")
    # NOT: HIGH akışında kanıt asimptotu = high_increment/(1-decay) = 1.0/0.4 = 2.5.
    # Eşik 2.5 ise asimptota EŞİT olduğu için ASLA aşılmaz (temporal CONFIRMED ölü
    # kod olur). 1.9 ile sürdürülen HIGH ~3 pencerede confirm olur; SUSPICIOUS-only
    # akış (asimptot 1.0) ise hiçbir zaman confirm olmaz.
    temporal_confirm_threshold: float = Field(default=1.9, alias="VEKTIA_TEMPORAL_CONFIRM_THRESHOLD")
    temporal_ttl_seconds: int = Field(default=120, alias="VEKTIA_TEMPORAL_TTL_SECONDS")

    # --- Per-Player Baseline & Trust (Faz 3 — Yanlış Pozitif Azaltma) ---
    # Global eşikler herkese aynı davranır; uzun süredir TEMİZ oynayan gerçek
    # oyuncu (ör. ritmik ama insan) ile yeni/şüpheli hesabı ayırmaz. Oyuncu başına
    # bir GÜVEN (trust) skoru biriktir (temiz-pencere EMA'sı). Güvenilen oyuncunun
    # şüpheli pencereleri zamansal kanıta DAHA AZ katkı yapsın (leniency) → kalıcı
    # gerçek oyuncuda FP daha da düşer; bot/yeni hesap tam hassasiyette kalır.
    baseline_enabled: bool = Field(default=True, alias="VEKTIA_BASELINE_ENABLED")
    baseline_ema_decay: float = Field(default=0.95, alias="VEKTIA_BASELINE_EMA_DECAY")
    baseline_min_samples: int = Field(default=50, alias="VEKTIA_BASELINE_MIN_SAMPLES")
    baseline_trust_leniency: float = Field(default=0.6, alias="VEKTIA_BASELINE_TRUST_LENIENCY")
    baseline_ttl_seconds: int = Field(default=86400, alias="VEKTIA_BASELINE_TTL_SECONDS")

    # --- Shadow Mode / Ölçüm (Faz 4 — Kalibrasyon) ---
    # shadow_mode=True iken pipeline kararı HESAPLAR ama AKSİYON ALMAZ: oyuncuyu
    # flag'lemez, ML kuyruğuna/ban'a göndermez; yalnızca "ne yapardım" sayaçlarını
    # işler. Yeni eşikleri canlıda, gerçek oyuncuyu etkilemeden ölçmek için.
    shadow_mode: bool = Field(default=False, alias="VEKTIA_SHADOW_MODE")

    # --- Ban Settings ---
    auto_ban_enabled: bool = Field(default=False, alias="VEKTIA_AUTO_BAN_ENABLED")
    ban_requires_admin_approval: bool = Field(
        default=True,
        alias="VEKTIA_BAN_REQUIRES_ADMIN_APPROVAL",
    )

    # --- Webhook ---
    webhook_timeout_seconds: int = Field(default=10, alias="VEKTIA_WEBHOOK_TIMEOUT_SECONDS")
    webhook_max_retries: int = Field(default=3, alias="VEKTIA_WEBHOOK_MAX_RETRIES")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Singleton Settings instance — uygulama ömrü boyunca tek bir kez oluşturulur."""
    return Settings()
