"""
Vektia API Middleware

Rate limiting, API key doğrulama, request loglama ve CORS yapılandırması.
"""

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
import time

from vektia.utils.security import validate_api_key, decode_jwt_token
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

# API Key header tanımı
api_key_header = APIKeyHeader(name="X-Vektia-Key", auto_error=False)


# ============================================
# API Key Dependency
# ============================================

async def verify_api_key(api_key: str = Security(api_key_header)) -> int:
    """
    API key doğrulama dependency'si.
    Veritabanından Müşteri (Client) doğrular ve client_id döner.
    """
    from vektia.db.database import get_session, Client
    from sqlalchemy import select

    if not api_key:
        raise HTTPException(status_code=401, detail="API key gerekli (X-Vektia-Key header)")
        
    async with get_session() as session:
        result = await session.execute(select(Client).where(Client.api_key == api_key))
        client = result.scalar_one_or_none()
        
        if not client or not client.is_active:
            raise HTTPException(status_code=403, detail="Geçersiz API key")
            
        return client.id


# ============================================
# JWT Auth Dependency
# ============================================

async def verify_jwt_token(request: Request) -> dict:
    """
    JWT token doğrulama dependency'si.
    Admin endpoint'lerinde kullanılır.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token gerekli")

    token = auth_header.replace("Bearer ", "")
    payload = decode_jwt_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token")

    return payload


# ============================================
# Request Logging Middleware
# ============================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Her isteği loglar ve yanıt süresini ölçer."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Sadece yavaş istekleri veya hataları logla (gürültüyü azalt)
        if duration_ms > 500 or response.status_code >= 400:
            logger.info(
                f"{request.method} {request.url.path} → "
                f"{response.status_code} ({duration_ms:.1f}ms)"
            )

        # Yanıt süresini header'a ekle
        response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"

        return response


# ============================================
# Rate Limiting (In-Memory Token Bucket)
# ============================================

class RateLimiter:
    """Basit in-memory rate limiter (IP bazlı)."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        """İsteğin izin verilip verilmediğini kontrol eder."""
        now = time.time()
        window_start = now - self.window_seconds

        if client_id not in self._requests:
            self._requests[client_id] = []

        # Pencere dışındaki eski istekleri temizle
        self._requests[client_id] = [
            t for t in self._requests[client_id] if t > window_start
        ]

        if len(self._requests[client_id]) >= self.max_requests:
            return False

        self._requests[client_id].append(now)
        return True


# Global rate limiters
telemetry_rate_limiter = RateLimiter(max_requests=200, window_seconds=60)
register_rate_limiter = RateLimiter(max_requests=3, window_seconds=3600) # 1 saatte 3 hesap
login_rate_limiter = RateLimiter(max_requests=10, window_seconds=60) # 1 dakikada 10 login denemesi
