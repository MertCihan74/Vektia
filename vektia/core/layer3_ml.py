"""
Vektia Layer 3 — Machine Learning Anomaly Detection

Katmanlı Elek'in üçüncü ve son katmanı. İlk iki katmandan
elenemeyen kritik %1'lik şüpheli havuzu için arka planda çalışan
hafif bir Isolation Forest modeli.

Isolation Forest, normal veri noktalarını izole etmek için daha fazla
bölme gerektirir; anomaliler ise çok az bölme ile izole edilebilir.
Bu özellik, etiketlenmemiş verilerle çalışmayı mümkün kılar.
"""

import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest

from vektia.core.models import StatsResult, RiskLevel
from vektia.utils.logger import get_logger

logger = get_logger(__name__)

# Model dosya yolu
MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"


class MLAnomalyDetector:
    """
    Katman 3: Isolation Forest Anomali Tespiti.

    Katman 2'nin istatistiksel metriklerini feature vektörü olarak alır
    ve çok boyutlu uzayda anomali skoru üretir.
    """

    def __init__(self):
        self.model: IsolationForest | None = None
        self.is_trained: bool = False
        self._load_model()

    def _load_model(self) -> None:
        """Disk'ten eğitilmiş modeli yükler (varsa)."""
        if MODEL_PATH.exists():
            try:
                self.model = joblib.load(MODEL_PATH)
                self.is_trained = True
                logger.info(f"ML modeli yüklendi: {MODEL_PATH}")
            except Exception as e:
                logger.error(f"Model yükleme hatası: {e}")
                self._init_default_model()
        else:
            self._init_default_model()

    def _init_default_model(self) -> None:
        """Eğitilmemiş varsayılan model oluşturur."""
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.05,  # %5 anomali oranı beklentisi
            max_samples="auto",
            random_state=42,
            n_jobs=-1,  # Tüm CPU çekirdeklerini kullan
        )
        self.is_trained = False
        logger.info("Varsayılan ML modeli oluşturuldu (eğitilmemiş)")

    def train(self, clean_data: list[StatsResult]) -> None:
        """
        Modeli "temiz" oyuncu verileriyle eğitir.

        Args:
            clean_data: Katman 2'den geçen temiz oyuncuların StatsResult listesi
        """
        if len(clean_data) < 50:
            logger.warning(f"Eğitim için yetersiz veri: {len(clean_data)} (min: 50)")
            return

        # Feature matrisini oluştur
        features = np.array([d.feature_vector for d in clean_data])

        self.model.fit(features)
        self.is_trained = True

        # Modeli diske kaydet
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, MODEL_PATH)
        logger.info(f"ML modeli eğitildi ({len(clean_data)} örnek) ve kaydedildi")

    def predict(self, stats_result: StatsResult) -> tuple[float, RiskLevel]:
        """
        Tek bir oyuncunun anomali skorunu hesaplar.

        Args:
            stats_result: Katman 2'nin ürettiği istatistiksel sonuç

        Returns:
            (anomaly_score, risk_level) tuple'ı
            anomaly_score: 0.0 (normal) - 1.0 (kesin anomali)
        """
        if not self.is_trained:
            # Model eğitilmemişse Katman 2'nin skorunu döndür
            logger.warning("ML modeli henüz eğitilmedi, Katman 2 skoru kullanılıyor")
            return stats_result.risk_score, stats_result.risk_level

        features = np.array([stats_result.feature_vector])

        # Isolation Forest: -1 = anomali, 1 = normal
        prediction = self.model.predict(features)[0]

        # Anomali skorunu (0=normal .. 1=anomali) MODELİN KENDİ karar sınırına
        # göre ölçekle. ÖNEMLİ DÜZELTME: Eskiden `-score_samples * 2` kullanılıyordu;
        # ama IsolationForest'ın score_samples'ı NORMAL noktalar için bile ~-0.45
        # civarındadır → normal insan da anomaly_score≈0.9 alıp yanlış flag yiyordu
        # (insan-FP'nin ana ML kaynağı). decision_function ise kontaminasyonla
        # kalibre edilmiş sınırı 0'a taşır: >0 normal, <0 anomali. Sınır etrafında
        # ölçekliyoruz. Eğim (ANOMALY_SLOPE) Faz 4'te gölge-mod ölçümüyle kalibre edilmeli.
        decision = float(self.model.decision_function(features)[0])  # >0 normal, <0 anomali
        raw_score = float(self.model.score_samples(features)[0])     # yalnızca loglama için
        ANOMALY_SLOPE = 5.0
        anomaly_score = float(np.clip(0.5 - ANOMALY_SLOPE * decision, 0.0, 1.0))

        # Katman 2 ve ML skorlarını birleştir (ağırlıklı).
        #
        # ÖNEMLİ (Faz 2 — Yanlış Pozitif Azaltma): Eskiden risk_score == 1.0
        # olduğunda ML tamamen by-pass edilip anında CONFIRMED veriliyordu.
        # Bu, Katman 2'nin kırılgan tek-pencere "hard" kurallarını temyiz
        # edilemez kılıyordu. Artık ML HER ZAMAN katkıda bulunur: model açıkça
        # "normal" diyorsa (prediction == 1 ve düşük anomali), heuristik 1.0
        # olsa bile gerçek oyuncu CONFIRMED yapılmaz; yalnızca HIGH (admin
        # incelemesi) olarak işaretlenir. Böylece ML bir güvenlik ağı görevi görür.
        combined_score = 0.6 * anomaly_score + 0.4 * stats_result.risk_score

        # CONFIRMED yalnızca İKİ kanıt birden güçlüyse: model anomali diyor
        # (prediction == -1) VE birleşik skor yeterince yüksek.
        if prediction == -1 and combined_score >= 0.6:
            risk_level = RiskLevel.CONFIRMED
        elif combined_score >= 0.85:
            risk_level = RiskLevel.CONFIRMED
        elif combined_score >= 0.6:
            risk_level = RiskLevel.HIGH
        elif combined_score >= 0.4:
            risk_level = RiskLevel.SUSPICIOUS
        else:
            risk_level = RiskLevel.CLEAN

        logger.info(
            f"[LAYER 3] ML analiz: {stats_result.player_id} | "
            f"raw={raw_score:.4f} anomaly={anomaly_score:.4f} "
            f"combined={combined_score:.4f} | {risk_level.value}"
        )

        return combined_score, risk_level

    def batch_predict(
        self, stats_results: list[StatsResult]
    ) -> list[tuple[str, float, RiskLevel]]:
        """
        Toplu anomali tespiti.

        Args:
            stats_results: StatsResult listesi

        Returns:
            (player_id, anomaly_score, risk_level) listesi
        """
        results = []
        for sr in stats_results:
            score, level = self.predict(sr)
            results.append((sr.player_id, score, level))
        return results


# Modül seviyesi singleton
ml_detector = MLAnomalyDetector()
