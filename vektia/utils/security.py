"""
Vektia Security Utilities

JWT token üretimi/doğrulama ve API key yönetimi.
Stateless authentication — sunucuda oturum tutmaz.
"""

import secrets
import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

from vektia.config import get_settings

# Bcrypt password hasher
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Şifreyi bcrypt ile hashler."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Şifreyi hash ile karşılaştırır."""
    return pwd_context.verify(plain_password, hashed_password)


def create_jwt_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    JWT token üretir.

    Args:
        data: Token payload'ına eklenecek veriler
        expires_delta: Özel süre (None ise config'den alınır)

    Returns:
        Kodlanmış JWT string
    """
    settings = get_settings()

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expiration_minutes)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_jwt_token(token: str) -> dict | None:
    """
    JWT token'ı çözer ve doğrular.

    Args:
        token: Kodlanmış JWT string

    Returns:
        Token payload dict'i veya geçersizse None
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def generate_api_key() -> str:
    """Rastgele 48 karakterlik API key üretir."""
    return f"vk_{secrets.token_urlsafe(36)}"


def validate_api_key(key: str) -> bool:
    """
    API key'i doğrular.

    MVP'de sadece master key ile karşılaştırır.
    Ölçeklenme aşamasında veritabanı sorgusu eklenecek.
    """
    settings = get_settings()
    return secrets.compare_digest(key, settings.master_api_key)
