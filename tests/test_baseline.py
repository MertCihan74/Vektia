"""
Per-Player Baseline / Trust Testleri (Faz 3 — Yanlış Pozitif Azaltma)

Güvence:
  - Yeni hesap (yetersiz örnek): leniency = 1.0 (normal hassasiyet).
  - Uzun süredir TEMİZ oynayan oyuncu: yüksek trust → leniency < 1.0 (korunur).
  - Sürekli HIGH üreten bot: trust ≈ 0 → leniency ≈ 1.0 (korunmaz, tam hassasiyet).
  - leniency, zamansal kanıt artışını gerçekten yavaşlatır (temporal entegrasyonu).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from vektia.core.models import RiskLevel, ActionType
from vektia.core.baseline import PlayerBaseline
from vektia.core.temporal import SuspicionTracker


class FakeRedis:
    """observe() için yeterli, bellek-içi minimal hash Redis taklidi."""

    def __init__(self):
        self.h = {}
        self.kv = {}

    async def hmget(self, key, *fields):
        d = self.h.get(key, {})
        return [d.get(f) for f in fields]

    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update({k: str(v) for k, v in (mapping or {}).items()})

    async def expire(self, key, ttl):
        pass

    # temporal entegrasyon testi için
    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = str(value)

    async def delete(self, *keys):
        for k in keys:
            self.h.pop(k, None)
            self.kv.pop(k, None)


SETTINGS = SimpleNamespace(
    baseline_enabled=True,
    baseline_ema_decay=0.95,
    baseline_min_samples=10,
    baseline_trust_leniency=0.6,
    baseline_ttl_seconds=3600,
)
SETTINGS_TEMPORAL = SimpleNamespace(
    temporal_enabled=True,
    temporal_decay_factor=0.6,
    temporal_high_increment=1.0,
    temporal_suspicious_increment=0.4,
    temporal_suspect_threshold=0.8,
    temporal_confirm_threshold=1.9,
    temporal_ttl_seconds=120,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_baseline():
    fake = FakeRedis()

    async def _gr():
        return fake

    return PlayerBaseline(), _gr


def observe(b, gr, risk, settings=SETTINGS):
    with patch("vektia.core.baseline.get_redis", gr), \
         patch("vektia.core.baseline.get_settings", lambda: settings):
        return run(b.observe(1, "p", ActionType.HIT, risk))


class TestPlayerBaseline:

    def test_new_player_no_leniency(self):
        """İlk pencerede (yetersiz örnek) leniency 1.0 olmalı."""
        b, gr = make_baseline()
        info = observe(b, gr, RiskLevel.CLEAN)
        assert info.leniency == 1.0
        assert info.samples == 1

    def test_trusted_player_gets_leniency(self):
        """Çok sayıda temiz pencere → yüksek trust → leniency belirgin biçimde < 1.0."""
        b, gr = make_baseline()
        info = None
        for _ in range(40):
            info = observe(b, gr, RiskLevel.CLEAN)
        assert info.samples >= SETTINGS.baseline_min_samples
        assert info.trust > 0.7
        assert info.leniency < 0.7   # 1 - 0.6*trust

    def test_bot_no_leniency(self):
        """Sürekli HIGH (bot) → trust ≈ 0 → leniency ≈ 1.0 (korunmaz)."""
        b, gr = make_baseline()
        info = None
        for _ in range(40):
            info = observe(b, gr, RiskLevel.HIGH)
        assert info.trust < 0.05
        assert info.leniency > 0.95

    def test_disabled_returns_neutral(self):
        """baseline_enabled=False → her zaman leniency 1.0."""
        b, gr = make_baseline()
        off = SimpleNamespace(**{**SETTINGS.__dict__, "baseline_enabled": False})
        info = observe(b, gr, RiskLevel.CLEAN, settings=off)
        assert info.leniency == 1.0

    def test_leniency_slows_temporal_confirm(self):
        """
        Entegrasyon: aynı sayıda HIGH pencerede, leniency=0.4 olan (güvenilen)
        oyuncunun kanıtı, leniency=1.0'a göre BELİRGİN biçimde daha düşük olmalı;
        ve confirm'e ulaşmamalı.
        """
        tracker = SuspicionTracker()
        fake = FakeRedis()

        async def _gr():
            return fake

        def rec(pid, leniency):
            with patch("vektia.core.temporal.get_redis", _gr), \
                 patch("vektia.core.temporal.get_settings", lambda: SETTINGS_TEMPORAL):
                return run(tracker.record(1, pid, ActionType.HIT, RiskLevel.HIGH, leniency=leniency))

        normal = trusted = None
        for _ in range(3):
            normal = rec("normal", 1.0)
            trusted = rec("trusted", 0.4)

        assert normal.evidence > trusted.evidence
        assert normal.tier == RiskLevel.CONFIRMED       # leniency yokken 3 pencerede confirm
        assert trusted.tier != RiskLevel.CONFIRMED      # güvenilen oyuncu confirm OLMAZ
