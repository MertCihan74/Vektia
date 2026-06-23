"""
Vektia Redis Client

Asenkron Redis bağlantı havuzu yönetimi ve Lua script işletimi.
Tüm Redis operasyonları bu modül üzerinden gerçekleştirilir.
"""

import redis.asyncio as aioredis
from pathlib import Path

from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

# Global Redis bağlantı havuzu
_redis_pool: aioredis.Redis | None = None

# Yüklenmiş Lua script SHA'ları
_lua_scripts: dict[str, str] = {}

# Lua script dosyalarının dizini
LUA_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts" / "redis_lua"


async def get_redis() -> aioredis.Redis:
    """Redis bağlantısını döndürür (lazy initialization)."""
    global _redis_pool
    if _redis_pool is None:
        await init_redis()
    return _redis_pool


async def init_redis() -> None:
    """
    Redis bağlantı havuzunu başlatır ve Lua scriptlerini yükler.
    Uygulama startup'ında çağrılır.
    """
    global _redis_pool

    settings = get_settings()

    _redis_pool = aioredis.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

    # Bağlantı testi
    try:
        await _redis_pool.ping()
        logger.info("Redis bağlantısı başarılı")
    except Exception as e:
        logger.error(f"Redis bağlantı hatası: {e}")
        raise

    # Lua scriptlerini yükle
    await _load_lua_scripts()


async def _load_lua_scripts() -> None:
    """scripts/redis_lua/ dizinindeki tüm .lua dosyalarını Redis'e yükler."""
    global _lua_scripts

    if not LUA_SCRIPTS_DIR.exists():
        logger.warning(f"Lua script dizini bulunamadı: {LUA_SCRIPTS_DIR}")
        return

    for lua_file in LUA_SCRIPTS_DIR.glob("*.lua"):
        script_name = lua_file.stem
        script_content = lua_file.read_text(encoding="utf-8")

        try:
            sha = await _redis_pool.script_load(script_content)
            _lua_scripts[script_name] = sha
            logger.info(f"Lua script yüklendi: {script_name} (SHA: {sha[:8]}...)")
        except Exception as e:
            logger.error(f"Lua script yükleme hatası ({script_name}): {e}")


async def execute_lua(script_name: str, keys: list, args: list) -> any:
    """
    Önceden yüklenmiş bir Lua scriptini çalıştırır.

    Args:
        script_name: Script dosya adı (uzantısız)
        keys: Redis key listesi (KEYS[])
        args: Argüman listesi (ARGV[])

    Returns:
        Script çıktısı
    """
    if script_name not in _lua_scripts:
        raise ValueError(f"Lua script bulunamadı: {script_name}")

    redis = await get_redis()
    return await redis.evalsha(_lua_scripts[script_name], len(keys), *keys, *args)


async def close_redis() -> None:
    """Redis bağlantısını kapatır. Uygulama shutdown'ında çağrılır."""
    global _redis_pool, _lua_scripts

    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        _lua_scripts.clear()
        logger.info("Redis bağlantısı kapatıldı")


async def is_redis_healthy() -> bool:
    """Redis sağlık kontrolü."""
    try:
        redis = await get_redis()
        return await redis.ping()
    except Exception:
        return False
