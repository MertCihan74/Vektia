"""
Vektia — FastAPI Application Entry Point

Tüm modülleri birleştiren ana uygulama dosyası.
Startup/shutdown lifecycle, route mounting ve static file serving.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from vektia.config import get_settings
from vektia.db.redis_client import init_redis, close_redis
from vektia.db.database import init_database, close_database
from vektia.db import event_buffer
from vektia.api.middleware import RequestLoggingMiddleware
from vektia.api.routes import health, telemetry, admin, webhook, customer
from vektia.api.websocket import router as ws_router
from vektia.worker.ml_worker import process_ml_queue
from vektia.worker.alert_worker import process_confirmed_bots
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

# Admin panel dosyalarının yolu
ADMIN_DIR = Path(__file__).parent.parent / "admin"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam döngüsü — başlangıç ve kapanış işlemleri."""
    settings = get_settings()

    # ═══ STARTUP ═══
    logger.info(f"🚀 {settings.app_name} v{settings.version} başlatılıyor...")

    # Redis bağlantısı
    await init_redis()
    logger.info("✅ Redis bağlantısı hazır")

    # Veritabanı
    await init_database()
    logger.info("✅ Veritabanı hazır")

    # Whitelist'i DB'den Redis set'ine senkronla (restart dayanıklılığı — ölçeklenme)
    await event_buffer.sync_whitelist_from_db()

    # ML Worker arka plan görevi
    ml_task = asyncio.create_task(_ml_worker_background())

    # Alert Worker arka plan görevi
    alert_task = asyncio.create_task(_alert_worker_background())

    # Subscription Worker arka plan görevi
    sub_task = asyncio.create_task(_subscription_worker_background())

    # Olay sayacı flush worker (Redis → Postgres toplu yazım — ölçeklenme)
    flush_task = asyncio.create_task(_event_flush_background())

    logger.info(f"✅ {settings.app_name} hazır — http://{settings.host}:{settings.port}")
    logger.info(f"📊 Admin Panel — http://{settings.host}:{settings.port}/admin/")

    yield

    # ═══ SHUTDOWN ═══
    logger.info("🛑 Kapatılıyor...")
    ml_task.cancel()
    alert_task.cancel()
    sub_task.cancel()
    flush_task.cancel()
    # Kapanmadan önce biriken son sayaçları DB'ye yaz (kayıp olmasın)
    try:
        await event_buffer.flush_pending_events()
    except Exception as e:
        logger.error(f"Kapanış flush hatası: {e}")
    await close_redis()
    await close_database()
    logger.info("👋 Kapatma tamamlandı")


async def _subscription_worker_background():
    """Abonelik durumlarını (süresi dolanlar) kontrol eden worker."""
    from vektia.db import repositories as repo
    while True:
        try:
            await repo.process_expired_subscriptions()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Subscription worker hatası: {e}")
        # Her 1 saatte bir kontrol et (Test için 1 dakika da yapılabilir, şu an 1 saat: 3600)
        await asyncio.sleep(3600)


async def _ml_worker_background():
    """ML worker'ı arka plan görevi olarak çalıştırır."""
    settings = get_settings()
    while True:
        try:
            await process_ml_queue()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"ML worker hatası: {e}")
        await asyncio.sleep(settings.ml_batch_interval_seconds)

async def _alert_worker_background():
    """Alert worker'ı arka plan görevi olarak çalıştırır (Otomatik ban, webhook)."""
    while True:
        try:
            await process_confirmed_bots()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Alert worker hatası: {e}")
        await asyncio.sleep(5)  # 5 saniyede bir kontrol et


async def _event_flush_background():
    """
    Olay sayacı flush worker'ı (ölçeklenme): Redis'te biriken olay sayaçlarını
    periyodik olarak TOPLU şekilde Postgres'e yazar. Hot-path'i Postgres'siz tutar.
    """
    while True:
        try:
            await event_buffer.flush_pending_events()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Event flush worker hatası: {e}")
        await asyncio.sleep(5)  # 5 saniyede bir flush


# ============================================
# FastAPI Application
# ============================================

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Event-Driven Behavioral Anti-Cheat & Anti-Scam API. "
        "Sunucu taraflı telemetri verisine dayanan katmanlı elek mimarisi."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ============================================
# Middleware
# ============================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da kısıtla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging
app.add_middleware(RequestLoggingMiddleware)

# ============================================
# Routes
# ============================================

app.include_router(health.router)
app.include_router(telemetry.router)
app.include_router(admin.router)
app.include_router(customer.router)
from vektia.api.routes import billing
app.include_router(billing.router)
app.include_router(webhook.router)
app.include_router(ws_router)

# ============================================
# Static Files (Admin Dashboard & Public)
# ============================================

if ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")

PUBLIC_DIR = Path(__file__).parent.parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public_dir")
    app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="public")
