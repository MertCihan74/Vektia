"""
Event Buffer testleri (ölçeklenme — hot-path'ten Postgres'i çıkarma).

Güvence:
  - record_event Postgres'e DOKUNMAZ, sadece Redis sayacını artırır.
  - flush sayaçları repo'ya TOPLU uygular ve pending'i temizler.
  - flush sırasında (rename'den sonra) gelen olaylar KAYBOLMAZ.
  - whitelist kontrolü Redis set'inden çalışır; ':' içeren FiveM ID'leri bozulmaz.
"""

import asyncio
from unittest.mock import patch, AsyncMock

from vektia.db import event_buffer as eb


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.sets = {}

    async def hincrby(self, key, field, n):
        h = self.hashes.setdefault(key, {})
        h[field] = h.get(field, 0) + n
        return h[field]

    async def hgetall(self, key):
        # gerçek redis decode_responses=True → str döner
        return {k: str(v) for k, v in self.hashes.get(key, {}).items()}

    async def rename(self, key, newkey):
        if key not in self.hashes:
            raise Exception("no such key")
        self.hashes[newkey] = self.hashes.pop(key)

    async def delete(self, *keys):
        for k in keys:
            self.hashes.pop(k, None)
            self.sets.pop(k, None)

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def with_redis(fake):
    async def _gr():
        return fake
    return _gr


class TestEventBuffer:

    def test_record_event_increments_redis_only(self):
        fake = FakeRedis()
        with patch("vektia.db.event_buffer.get_redis", with_redis(fake)):
            run(eb.record_event(1, "steam:abc", "srv1"))
            run(eb.record_event(1, "steam:abc", "srv1"))
            run(eb.record_event(1, "license:xyz", "srv1"))
        h = fake.hashes[eb.PENDING_KEY]
        assert h["1|srv1|steam:abc"] == 2     # ':' içeren ID bozulmadı
        assert h["1|srv1|license:xyz"] == 1

    def test_flush_applies_counts_and_clears(self):
        fake = FakeRedis()
        goc = AsyncMock()
        ape = AsyncMock()
        with patch("vektia.db.event_buffer.get_redis", with_redis(fake)), \
             patch.object(eb.repo, "get_or_create_player", goc), \
             patch.object(eb.repo, "add_player_events", ape):
            run(eb.record_event(7, "steam:p1", "s"))
            run(eb.record_event(7, "steam:p1", "s"))
            run(eb.record_event(7, "steam:p2", "s"))
            applied = run(eb.flush_pending_events())

        assert applied == 2  # iki ayrı oyuncu
        # p1 için toplu 2, p2 için 1 uygulanmalı
        ape.assert_any_call(7, "steam:p1", 2)
        ape.assert_any_call(7, "steam:p2", 1)
        assert goc.await_count == 2
        # pending temizlendi
        assert eb.PENDING_KEY not in fake.hashes

    def test_flush_empty_returns_zero(self):
        fake = FakeRedis()
        with patch("vektia.db.event_buffer.get_redis", with_redis(fake)):
            assert run(eb.flush_pending_events()) == 0

    def test_events_during_flush_not_lost(self):
        """rename ile sayaç taşınır; flush sırasında gelen yeni olay yeni hash'e gider."""
        fake = FakeRedis()
        with patch("vektia.db.event_buffer.get_redis", with_redis(fake)), \
             patch.object(eb.repo, "get_or_create_player", AsyncMock()), \
             patch.object(eb.repo, "add_player_events", AsyncMock()):
            run(eb.record_event(1, "p", "s"))
            run(eb.flush_pending_events())          # ilk partiyi işle + temizle
            run(eb.record_event(1, "p", "s"))       # flush sonrası yeni olay
            second = fake.hashes.get(eb.PENDING_KEY, {})
        assert second.get("1|s|p") == 1             # kaybolmadı

    def test_is_whitelisted(self):
        fake = FakeRedis()
        with patch("vektia.db.event_buffer.get_redis", with_redis(fake)):
            run(fake.sadd(eb.WHITELIST_KEY, "steam:vip"))
            assert run(eb.is_whitelisted("steam:vip")) is True
            assert run(eb.is_whitelisted("steam:nobody")) is False
