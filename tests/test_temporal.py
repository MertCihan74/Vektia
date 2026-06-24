"""
Zamansal Kanıt Biriktirici Testleri (Faz 1 — Yanlış Pozitif Azaltma)

Asıl güvence: TEK BİR şüpheli/HIGH pencere asla CONFIRMED üretmez.
Kesin karar yalnızca SÜRDÜRÜLEN kanıt (birden çok ardışık pencere) oluşunca verilir.
İzole bir HIGH penceresi, sonraki temiz pencerelerde söner ve karara dönüşmez.
"""

import asyncio
from unittest.mock import patch

import pytest

from vektia.core.models import RiskLevel, ActionType
from vektia.core.temporal import SuspicionTracker


class FakeRedis:
    """record() için yeterli, bellek-içi minimal Redis taklidi."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = str(value)

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_tracker():
    fake = FakeRedis()

    async def _get_redis():
        return fake

    tracker = SuspicionTracker()
    return tracker, _get_redis


def record(tracker, get_redis, risk):
    with patch("vektia.core.temporal.get_redis", get_redis):
        return run(tracker.record(1, "p", ActionType.HIT, risk))


class TestTemporalAggregator:

    def test_single_high_window_never_confirmed(self):
        """Tek bir HIGH pencere ASLA kesin karar (CONFIRMED) üretmemeli."""
        tracker, gr = make_tracker()
        d = record(tracker, gr, RiskLevel.HIGH)
        assert d.tier != RiskLevel.CONFIRMED
        assert d.sustained is False

    def test_sustained_high_eventually_confirmed(self):
        """Ardışık HIGH pencereler birikip CONFIRMED'e ulaşmalı."""
        tracker, gr = make_tracker()
        last = None
        confirmed_at = None
        for i in range(1, 6):
            last = record(tracker, gr, RiskLevel.HIGH)
            if last.tier == RiskLevel.CONFIRMED and confirmed_at is None:
                confirmed_at = i
        assert last.tier == RiskLevel.CONFIRMED
        # İlk pencerede değil, birikim sonrası (>=3) confirmed olmalı
        assert confirmed_at is not None and confirmed_at >= 3

    def test_isolated_high_decays_without_confirm(self):
        """İzole bir HIGH, sonraki temiz pencerelerde sönmeli; asla confirmed olmamalı."""
        tracker, gr = make_tracker()
        record(tracker, gr, RiskLevel.HIGH)  # tek sıçrama
        final = None
        for _ in range(4):
            final = record(tracker, gr, RiskLevel.CLEAN)  # temiz pencereler
        assert final.tier == RiskLevel.CLEAN
        assert final.evidence < 0.8  # suspect eşiğinin altına sönmüş

    def test_pure_suspicious_never_confirms(self):
        """Sürekli SUSPICIOUS (HIGH değil) pencereler asla CONFIRMED olmamalı."""
        tracker, gr = make_tracker()
        last = None
        for _ in range(15):
            last = record(tracker, gr, RiskLevel.SUSPICIOUS)
        # Kararlı durum ~ inc/(1-decay) = 0.4/0.4 = 1.0 < confirm(2.5)
        assert last.tier != RiskLevel.CONFIRMED

    def test_clean_window_returns_clean_tier(self):
        """Temiz pencere düşük kanıtla CLEAN tier dönmeli."""
        tracker, gr = make_tracker()
        d = record(tracker, gr, RiskLevel.CLEAN)
        assert d.tier == RiskLevel.CLEAN
        assert d.sustained is False
