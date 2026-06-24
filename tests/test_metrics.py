"""
Faz 4 — Ölçüm metrikleri testleri (saf fonksiyonlar, bağımlılık yok).
"""

from vektia.core.metrics import false_positive_rate, shadow_flag_rate


class TestFalsePositiveRate:

    def test_no_action_is_zero(self):
        assert false_positive_rate(0, 0, 0) == 0.0

    def test_all_whitelisted_is_one(self):
        # Aksiyon alınan herkes geri çevrildiyse FP oranı 1.0
        assert false_positive_rate(0, 0, 5) == 1.0

    def test_typical_low_rate(self):
        # 90 flag + 5 ban aksiyonu, 5'i whitelist (FP) → 5/100 = 0.05
        assert false_positive_rate(90, 5, 5) == 0.05

    def test_half(self):
        assert false_positive_rate(10, 0, 10) == 0.5

    def test_handles_none_and_negative(self):
        assert false_positive_rate(None, None, None) == 0.0
        assert false_positive_rate(-3, 0, 0) == 0.0


class TestShadowFlagRate:

    def test_no_events_is_zero(self):
        assert shadow_flag_rate(10, 0) == 0.0

    def test_basic_ratio(self):
        assert shadow_flag_rate(25, 1000) == 0.025

    def test_handles_none(self):
        assert shadow_flag_rate(None, 100) == 0.0
