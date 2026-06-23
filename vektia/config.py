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
    max_window: int = Field(default=20, alias="VEKTIA_MAX_WINDOW")
    bot_threshold: float = Field(default=0.005, alias="VEKTIA_BOT_THRESHOLD")
    suspicious_threshold: float = Field(default=0.02, alias="VEKTIA_SUSPICIOUS_THRESHOLD")
    player_ttl_seconds: int = Field(default=300, alias="VEKTIA_PLAYER_TTL_SECONDS")
    ml_batch_interval_seconds: int = Field(default=30, alias="VEKTIA_ML_BATCH_INTERVAL_SECONDS")

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
