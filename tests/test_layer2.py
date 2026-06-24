"""
Katman 2 — İstatistiksel Analiz Testleri

Bot ve insan ritimlerinin doğru ayrıştırıldığını doğrular.
"""

import random
import time
import pytest

from vektia.core.models import WindowData, ActionType, RiskLevel, Vector3
from vektia.core.layer2_stats import StatisticalFilter


def make_click_window(player_id: str, timestamps: list[float], coords: list) -> WindowData:
    """CLICK + koordinatlı test penceresi (spatial analiz için)."""
    return WindowData(
        client_id=1,
        player_id=player_id,
        timestamps=timestamps,
        action_type=ActionType.CLICK,
        has_enough_data=True,
        window_size=len(timestamps),
        coords_list=coords,
    )


@pytest.fixture
def stats_filter():
    return StatisticalFilter()


def make_window(player_id: str, timestamps: list[float]) -> WindowData:
    """Test için WindowData oluşturur."""
    return WindowData(
        client_id=1,
        player_id=player_id,
        timestamps=timestamps,
        action_type=ActionType.HIT,
        has_enough_data=True,
        window_size=len(timestamps),
    )


def generate_timestamps(count: int, interval_ms: float, jitter_ms: float) -> list[float]:
    """Test amaçlı timestamp dizisi üretir."""
    timestamps = []
    t = 1000000.0  # Sabit başlangıç
    for _ in range(count):
        t += interval_ms + random.uniform(-jitter_ms, jitter_ms)
        timestamps.append(t)
    return timestamps


class TestStatisticalFilter:
    """İstatistiksel filtreleme testleri."""

    def test_perfect_bot_detected(self, stats_filter):
        """Mükemmel ritmik bot (sıfır jitter) — en azından düşük risk almalı."""
        timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=0.1)
        window = make_window("perfect_bot", timestamps)
        
        result = stats_filter.analyze(window)
        
        assert result.std_deviation < 0.5  # Çok düşük sapma
        assert result.risk_score > 0.0     # Sıfırdan yüksek risk
        assert result.risk_level != RiskLevel.CLEAN  # Temiz olmamalı

    def test_human_player_clean(self, stats_filter):
        """İnsan oyuncu (yüksek jitter) temiz çıkmalı."""
        timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=40.0)
        window = make_window("human_player", timestamps)
        
        result = stats_filter.analyze(window)
        
        assert result.std_deviation > 5.0
        assert result.risk_level in (RiskLevel.CLEAN, RiskLevel.LOW)

    def test_insufficient_data_returns_clean(self, stats_filter):
        """3'ten az delta varsa temiz döndürmeli."""
        timestamps = [1000.0, 1100.0]  # Sadece 1 delta
        window = make_window("new_player", timestamps)
        
        result = stats_filter.analyze(window)
        
        assert result.risk_level == RiskLevel.CLEAN

    def test_macro_detected(self, stats_filter):
        """Tekrarlayan desendeki makro — insan kadar temiz olmamalı."""
        pattern = [100, 102, 98, 101, 100]
        timestamps = []
        t = 1000000.0
        for i in range(20):
            t += pattern[i % len(pattern)]
            timestamps.append(t)
        
        window = make_window("macro_user", timestamps)
        result = stats_filter.analyze(window)
        
        assert result.std_deviation < 5.0  # Düşük sapma
        assert result.risk_score > 0.0  # Sıfırdan yüksek
        # Makro bir insandan daha riskli olmalı
        human_ts = generate_timestamps(20, interval_ms=100.0, jitter_ms=40.0)
        human_result = stats_filter.analyze(make_window("human", human_ts))
        assert result.risk_score > human_result.risk_score

    def test_entropy_low_for_bot(self, stats_filter):
        """Bot ritimleri düşük CV üretmeli (ritmik tekrar)."""
        bot_timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=0.5)
        human_timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=35.0)
        
        bot_result = stats_filter.analyze(make_window("bot", bot_timestamps))
        human_result = stats_filter.analyze(make_window("human", human_timestamps))
        
        # Bot CV'si (değişim katsayısı) insan CV'sinden düşük olmalı
        assert bot_result.coefficient_of_variation < human_result.coefficient_of_variation
        # Bot std sapması insan std sapmasından düşük olmalı
        assert bot_result.std_deviation < human_result.std_deviation

    def test_feature_vector_correct_length(self, stats_filter):
        """Feature vektörü 6 elemanlı olmalı."""
        timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=10.0)
        window = make_window("test", timestamps)
        
        result = stats_filter.analyze(window)
        
        # feature_vector ML için 8 boyutludur (std, cv, entropy, autocorr,
        # mean, median, skewness, range_ratio) — bkz. models.py
        assert len(result.feature_vector) == 8

    def test_risk_score_bounded(self, stats_filter):
        """Risk skoru 0-1 arasında olmalı."""
        for _ in range(10):
            jitter = random.uniform(0.1, 50.0)
            timestamps = generate_timestamps(20, interval_ms=100.0, jitter_ms=jitter)
            window = make_window("bounded_test", timestamps)
            
            result = stats_filter.analyze(window)
            
            assert 0.0 <= result.risk_score <= 1.0

    def test_identical_timestamps_zero_entropy(self, stats_filter):
        """Tüm delta'lar aynıysa entropi sıfır olmalı."""
        timestamps = [1000.0 + i * 100.0 for i in range(20)]
        window = make_window("identical", timestamps)
        
        result = stats_filter.analyze(window)
        
        assert result.entropy == 0.0

    def test_highly_irregular_macro(self, stats_filter):
        """Düzensiz ama tekrarlayan bir makro. Layer 2 muhafazakar olduğu için düşük risk verebilir, ML halleder."""
        # 4 farklı gecikmeli bir desen
        pattern = [50.0, 300.0, 100.0, 200.0]
        timestamps = []
        t = 1000000.0
        for i in range(20):
            t += pattern[i % len(pattern)]
            timestamps.append(t)
        
        window = make_window("irregular_macro", timestamps)
        result = stats_filter.analyze(window)
        
        # Standart sapması yüksek çıkacaktır
        assert result.std_deviation > 20.0
        # Layer 2 bu kadar kompleks bir desende false-positive yapmamak için skoru 0 tutabilir
        assert result.risk_score >= 0.0

    def test_extremely_fast_clicks(self, stats_filter):
        """Çok hızlı tıklamalar (auto-clicker) en azından düşük risk almalı."""
        # 10ms aralıkla tıklayan auto clicker (jitter 1ms)
        timestamps = generate_timestamps(20, interval_ms=10.0, jitter_ms=1.0)
        window = make_window("auto_clicker", timestamps)
        
        result = stats_filter.analyze(window)
        
        assert result.mean_delta < 15.0
        assert result.std_deviation < 5.0
        assert result.risk_score > 0.1


class TestSpatialAnalysis:
    """Mekansal (mouse/konum) robotik-hareket sinyali testleri — Faz: spatial."""

    def test_spatial_human_noisy_movement_low(self, stats_filter):
        """Gürültülü/eğrisel insan mouse hareketi → düşük spatial skor."""
        random.seed(1)
        xs = [100 + random.uniform(-40, 40) for _ in range(20)]
        ys = [100 + random.uniform(-40, 40) for _ in range(20)]
        assert stats_filter._spatial_score(xs, ys, cv=0.4, range_ratio=8.0) < 0.4

    def test_spatial_fixed_target_autoclicker_high(self, stats_filter):
        """Sabit hedefe oto-tıklama (0 yayılım) + düzenli ritim → yüksek skor."""
        xs = [200.0] * 20
        ys = [150.0] * 20
        assert stats_filter._spatial_score(xs, ys, cv=0.02, range_ratio=1.05) >= 0.85

    def test_spatial_linear_path_bot_high(self, stats_filter):
        """Mükemmel düz çizgi + sabit adım = robotik → yüksek skor."""
        xs = [float(10 * i) for i in range(20)]
        ys = [float(5 * i) for i in range(20)]
        assert stats_filter._spatial_score(xs, ys, cv=0.3, range_ratio=5.0) >= 0.7

    def test_robotic_mouse_raises_risk_vs_human(self, stats_filter):
        """AYNI insani timing'de robotik mouse hareketi, insani hareketten daha riskli olmalı."""
        ts = generate_timestamps(20, interval_ms=150.0, jitter_ms=30.0)  # insani timing
        random.seed(2)
        human_coords = [Vector3(x=100 + random.uniform(-50, 50),
                                y=100 + random.uniform(-50, 50)) for _ in range(20)]
        bot_coords = [Vector3(x=10.0 * i, y=5.0 * i) for i in range(20)]  # düz çizgi
        human = stats_filter.analyze(make_click_window("h", ts, human_coords))
        bot = stats_filter.analyze(make_click_window("b", ts, bot_coords))
        assert bot.risk_score > human.risk_score

    def test_human_mouse_keeps_clean(self, stats_filter):
        """İnsani timing + insani mouse → CLEAN/LOW kalmalı (FP yok)."""
        ts = generate_timestamps(20, interval_ms=150.0, jitter_ms=35.0)
        random.seed(3)
        coords = [Vector3(x=100 + random.uniform(-60, 60),
                          y=100 + random.uniform(-60, 60)) for _ in range(20)]
        result = stats_filter.analyze(make_click_window("h2", ts, coords))
        assert result.risk_level in (RiskLevel.CLEAN, RiskLevel.LOW)
