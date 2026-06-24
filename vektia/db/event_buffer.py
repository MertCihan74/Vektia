"""
Vektia Event Buffer — Ölçeklenme (hot-path'ten Postgres'i çıkar)

SORUN: Pipeline her telemetri olayında 2 Postgres yazması yapıyordu
(get_or_create_player + increment_player_events). Redis saniyede milyonları
kaldırır ama Postgres her olayda yazınca asıl darboğaz buydu.

ÇÖZÜM: Hot-path'i tamamen Redis'e taşı —
  - Olay sayacı Redis hash'inde biriktirilir (HINCRBY — O(1), in-memory).
  - 'whitelisted' kontrolü Redis set'inden yapılır (DB yok).
  - Bir arka-plan görevi (flush_pending_events) sayaçları periyodik olarak
    Postgres'e TOPLU uygular (get_or_create + add_player_events). İlk flush
    oyuncu satırını da oluşturur.
Postgres yalnızca flush'ta (periyodik, toplu) ve şüpheli olaylarda (nadir,
filtre sonrası) yazılır. Eventual consistency: sayaçlar birkaç saniye gecikmeyle
DB'ye yansır — analitik için kabul edilebilir.
"""

import uuid

from vektia.db.redis_client import get_redis
from vektia.db import repositories as repo
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

PENDING_KEY = "vektia:pending_events"   # hash: "{cid}|{sid}|{pid}" -> count
WHITELIST_KEY = "vektia:whitelisted"    # set: player_id (admin endpoint de bunu kullanır)

# Alan ayırıcı: client_id (int) ve server_id ilk iki parçada; player_id (içinde
# ':' olabilen FiveM identifier'ı) SON parça olduğu için split(maxsplit=2) güvenli.
_SEP = "|"


async def record_event(client_id: int, player_id: str, server_id: str | None = None) -> None:
    """Olayı Redis sayacına ekler (Postgres'e DOKUNMAZ)."""
    try:
        redis = await get_redis()
        field = f"{client_id}{_SEP}{server_id or ''}{_SEP}{player_id}"
        await redis.hincrby(PENDING_KEY, field, 1)
    except Exception as e:
        logger.error(f"Olay sayacı (record_event) hatası: {e}")


async def is_whitelisted(player_id: str) -> bool:
    """Oyuncu whitelist'te mi? Redis set'inden O(1) (DB yok)."""
    try:
        redis = await get_redis()
        return bool(await redis.sismember(WHITELIST_KEY, player_id))
    except Exception as e:
        logger.error(f"Whitelist kontrol hatası: {e}")
        return False


async def flush_pending_events() -> int:
    """
    Birikmiş olay sayaçlarını Postgres'e TOPLU uygular. Arka-plan görevinden çağrılır.

    Atomik al-ve-temizle: RENAME ile sayaç hash'ini geçici anahtara taşı (bu sırada
    gelen yeni olaylar yeni hash'e gider, kaybolmaz), sonra geçiciyi işle ve sil.

    Returns: işlenen (oyuncu) kayıt sayısı.
    """
    redis = await get_redis()
    tmp_key = f"{PENDING_KEY}:flushing:{uuid.uuid4().hex}"

    try:
        await redis.rename(PENDING_KEY, tmp_key)
    except Exception:
        return 0  # PENDING_KEY yok = işlenecek bir şey yok

    try:
        pending = await redis.hgetall(tmp_key)
    finally:
        try:
            await redis.delete(tmp_key)
        except Exception as e:
            logger.error(f"Flush temp temizleme hatası: {e}")

    applied = 0
    for field, count in (pending or {}).items():
        try:
            cid_s, sid, pid = field.split(_SEP, 2)
            cid = int(cid_s)
            await repo.get_or_create_player(cid, pid, sid or None)
            await repo.add_player_events(cid, pid, int(count))
            applied += 1
        except Exception as e:
            logger.error(f"Flush uygulama hatası ({field!r}): {e}")

    if applied:
        logger.info(f"Event buffer flush: {applied} oyuncu sayacı DB'ye yazıldı")
    return applied


async def sync_whitelist_from_db() -> int:
    """
    Başlangıçta DB'deki whitelisted oyuncuları Redis set'ine yükler.
    Redis sıfırlanmış olsa bile (restart) whitelist enforcement dayanıklı kalır.
    """
    try:
        ids = await repo.get_whitelisted_player_ids()
        if ids:
            redis = await get_redis()
            await redis.sadd(WHITELIST_KEY, *ids)
        logger.info(f"Whitelist senkronu: {len(ids)} oyuncu Redis set'ine yüklendi")
        return len(ids)
    except Exception as e:
        logger.error(f"Whitelist sync hatası: {e}")
        return 0
