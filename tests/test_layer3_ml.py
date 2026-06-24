"""
Katman 3 — Machine Learning Anomali Tespiti Testleri

Isolation Forest modelinin eğitim ve tahmin (prediction) fonksiyonlarını,
mock verilerle (sahte verilerle) test eder.
"""

import pytest
import numpy as np

from vektia.core.models import StatsResult, RiskLevel
from vektia.core.layer3_ml import MLAnomalyDetector


@pytest.fixture
def clean_mock_data():
    """Modeli eğitmek için 60 adet 'temiz' (insan benzeri) oyuncu verisi üretir."""
    data = []
    for i in range(60):
        # Normal insan özellikleri (Gauss dağılımı ile küme oluştur):
        sr = StatsResult(
            client_id=1,
            player_id=f"clean_human_{i}",
            std_deviation=np.clip(np.random.normal(35.0, 5.0), 20.0, 60.0),
            coefficient_of_variation=np.clip(np.random.normal(0.25, 0.05), 0.1, 0.5),
            entropy=np.clip(np.random.normal(0.85, 0.05), 0.6, 1.0),
            autocorrelation=np.clip(np.random.normal(0.05, 0.1), -0.5, 0.5),
            mean_delta=np.random.normal(110.0, 15.0),
            median_delta=np.random.normal(105.0, 15.0),
            risk_level=RiskLevel.CLEAN,
            risk_score=0.0
        )
        data.append(sr)
    return data


@pytest.fixture
def bot_mock_data():
    """Test için 'bot/makro' profiline uyan bir anomali verisi üretir."""
    # Düşük std_dev, çok düşük CV, çok düşük entropi, çok yüksek otokorelasyon
    return StatsResult(
        client_id=1,
        player_id="evil_bot",
        std_deviation=0.5,
        coefficient_of_variation=0.005,
        entropy=0.1,
        autocorrelation=0.9,
        mean_delta=100.0,
        median_delta=100.0,
        risk_level=RiskLevel.SUSPICIOUS,
        risk_score=0.4
    )


@pytest.fixture
def human_test_data():
    """Test için 'temiz insan' profiline uyan bir veri üretir."""
    return StatsResult(
        client_id=1,
        player_id="test_human",
        std_deviation=35.0,
        coefficient_of_variation=0.25,
        entropy=0.85,
        autocorrelation=0.05,
        mean_delta=110.0,
        median_delta=105.0,
        risk_level=RiskLevel.CLEAN,
        risk_score=0.0
    )


class TestMLAnomalyDetector:
    """Layer 3 Isolation Forest testleri."""

    def test_initialization_without_model(self):
        """Model ilk oluşturulduğunda eğitilmemiş (untrained) olmalı."""
        detector = MLAnomalyDetector()
        # Test ortamında var olan joblib dosyasını yoksaymak için yeniden init
        detector._init_default_model()
        
        assert detector.is_trained is False
        assert detector.model is not None

    def test_predict_untrained_fallback(self):
        """Model eğitilmemişse predict, Katman 2'nin orijinal skorunu dönmeli."""
        detector = MLAnomalyDetector()
        detector._init_default_model()
        
        test_sr = StatsResult(
            client_id=1,
            player_id="test", std_deviation=10, coefficient_of_variation=0.1,
            entropy=0.5, autocorrelation=0.5, mean_delta=100, median_delta=100,
            risk_level=RiskLevel.SUSPICIOUS, risk_score=0.35
        )
        
        score, level = detector.predict(test_sr)
        
        # Eğitilmediği için fallback olarak test_sr içindeki değeri dönecektir
        assert score == 0.35
        assert level == RiskLevel.SUSPICIOUS

    def test_train_model_with_clean_data(self, clean_mock_data):
        """Temiz verilerle train() metodu çağrıldığında is_trained True olmalı."""
        detector = MLAnomalyDetector()
        detector._init_default_model()
        
        detector.train(clean_mock_data)
        
        assert detector.is_trained is True

    def test_predict_anomaly_detection(self, clean_mock_data, bot_mock_data, human_test_data):
        """Eğitilmiş model, botu anomali (high risk) olarak ayırabilmeli."""
        detector = MLAnomalyDetector()
        detector._init_default_model()
        
        # 1. Modeli temiz verilerle eğit (Sadece insan profilini normal kabul etsin)
        detector.train(clean_mock_data)
        
        # 2. İnsan profilini test et (Anomali skoru düşük olmalı)
        human_score, human_level = detector.predict(human_test_data)
        
        # 3. Bot profilini test et (Anomali skoru yüksek olmalı)
        bot_score, bot_level = detector.predict(bot_mock_data)
        
        # Beklentiler:
        # Bot skoru, insan skorundan anlamlı şekilde yüksek olmalıdır
        assert bot_score > human_score + 0.1
        # Bot'un son risk seviyesi şüpheli veya daha kötü olmalıdır
        assert bot_level in (RiskLevel.SUSPICIOUS, RiskLevel.HIGH, RiskLevel.CONFIRMED)
        # İnsan skoru 0.5'ten küçük olmalıdır (kesin anomali olmamalıdır)
        assert human_score < 0.5
