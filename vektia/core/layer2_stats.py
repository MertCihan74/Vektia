"""
Vektia Layer 2 — Statistical Deviation Filter

Katmanlı Elek'in ikinci katmanı. İnsan ve bot ritmini matematiksel
olarak ayırt eder.

İnsan ritimleri kaotiktir — milisaniyelik sapmalar yüksektir.
Bot/makro ritimleri algoritmiktir — sapmalar sıfıra yakındır.

Kullanılan metrikler:
- Standart Sapma (Standard Deviation)
- Değişim Katsayısı (Coefficient of Variation)
- Shannon Entropisi (bilgi karmaşıklığı)
- Otokorelasyon (ardışık desenlerin tekrarı)
"""

import numpy as np
from collections import Counter

from vektia.core.models import WindowData, StatsResult, RiskLevel
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


class StatisticalFilter:
    """
    Katman 2: İstatistiksel sapma analizi.
    
    Son N tıklama arasındaki zaman farklarının (Delta Time)
    istatistiksel özelliklerini hesaplayarak bot/insan ayrımı yapar.
    """

    def analyze(self, window_data: WindowData) -> StatsResult:
        """
        Pencere verisini istatistiksel olarak analiz eder.
        
        Args:
            window_data: Katman 1'den gelen pencere verisi
            
        Returns:
            StatsResult — tüm istatistiksel metrikler ve risk değerlendirmesi
        """
        settings = get_settings()
        timestamps = np.array(window_data.timestamps, dtype=np.float64)

        # Tıklamalar arasındaki zaman farkları (Delta Time)
        # timestamps LPUSH ile eklendiği için ters sırada — düzelt
        timestamps_sorted = np.sort(timestamps)
        deltas = np.diff(timestamps_sorted)

        # Sıfır veya negatif delta'ları filtrele (olası duplicate event)
        deltas = deltas[deltas > 0]

        if len(deltas) < 3:
            return StatsResult(
                client_id=window_data.client_id,
                player_id=window_data.player_id,
                risk_level=RiskLevel.CLEAN,
                risk_score=0.0,
            )

        # === Metrik Hesaplamaları ===

        # 1. Standart Sapma — Ana metrik
        std_deviation = float(np.std(deltas))

        # 2. Ortalama ve Medyan Delta
        mean_delta = float(np.mean(deltas))
        median_delta = float(np.median(deltas))

        # 3. Değişim Katsayısı (CV) — Farklı hızlardaki oyuncuları normalize eder
        cv = float(std_deviation / mean_delta) if mean_delta > 0 else 0.0

        # 4. Shannon Entropisi — Bot'lar düşük entropi üretir
        entropy = self._calculate_entropy(deltas)

        # 5. Otokorelasyon — Makrolar yüksek otokorelasyon gösterir
        autocorrelation = self._calculate_autocorrelation(deltas)

        # === Risk Değerlendirmesi ===
        risk_score, risk_level = self._evaluate_risk(
            std_deviation=std_deviation,
            cv=cv,
            entropy=entropy,
            autocorrelation=autocorrelation,
            bot_threshold=settings.bot_threshold,
            suspicious_threshold=settings.suspicious_threshold,
        )

        result = StatsResult(
            client_id=window_data.client_id,
            player_id=window_data.player_id,
            std_deviation=std_deviation,
            coefficient_of_variation=cv,
            entropy=entropy,
            autocorrelation=autocorrelation,
            mean_delta=mean_delta,
            median_delta=median_delta,
            risk_level=risk_level,
            risk_score=risk_score,
        )

        if risk_level in (RiskLevel.SUSPICIOUS, RiskLevel.HIGH):
            logger.info(
                f"[LAYER 2] Şüpheli tespit: {window_data.player_id} | "
                f"STD={std_deviation:.6f} CV={cv:.4f} ENT={entropy:.4f} "
                f"AC={autocorrelation:.4f} | Risk: {risk_level.value} ({risk_score:.2f})"
            )

        return result

    def _calculate_entropy(self, deltas: np.ndarray, bins: int = 10) -> float:
        """
        Shannon Entropisi hesaplar.
        
        Delta'ları bin'lere bölerek olasılık dağılımı oluşturur.
        Yüksek entropi = kaotik (insan), düşük entropi = düzenli (bot).
        """
        if len(deltas) < 2:
            return 0.0

        # Delta'ları yuvarla ve bin'le
        delta_range = np.max(deltas) - np.min(deltas)
        if delta_range == 0:
            return 0.0  # Tüm delta'lar aynı → sıfır entropi (kesin bot)

        bin_size = delta_range / bins
        if bin_size == 0:
            return 0.0

        binned = np.floor((deltas - np.min(deltas)) / bin_size).astype(int)
        binned = np.clip(binned, 0, bins - 1)  # Sınır kontrolü

        counts = Counter(binned.tolist())
        total = len(binned)
        probabilities = [count / total for count in counts.values()]

        # Shannon Entropy: H = -Σ p(x) * log2(p(x))
        entropy = -sum(p * np.log2(p) for p in probabilities if p > 0)

        # Normalize (0-1 arası)
        max_entropy = np.log2(bins)
        return float(entropy / max_entropy) if max_entropy > 0 else 0.0

    def _calculate_autocorrelation(self, deltas: np.ndarray, lag: int = 1) -> float:
        """
        Ardışık delta'lar arası otokorelasyon hesaplar.
        
        Yüksek otokorelasyon = tekrarlayan desen (makro şüphesi).
        Düşük otokorelasyon = rastgele dağılım (insan).
        """
        if len(deltas) < lag + 2:
            return 0.0

        n = len(deltas)
        mean = np.mean(deltas)
        variance = np.var(deltas)

        if variance == 0:
            return 1.0  # Sıfır varyans = mükemmel korelasyon = kesin bot

        # Lag-k otokorelasyon
        autocov = np.sum((deltas[:n - lag] - mean) * (deltas[lag:] - mean)) / n
        return float(autocov / variance)

    def _evaluate_risk(
        self,
        std_deviation: float,
        cv: float,
        entropy: float,
        autocorrelation: float,
        bot_threshold: float,
        suspicious_threshold: float,
    ) -> tuple[float, RiskLevel]:
        """
        Birden fazla metriği birleştirerek nihai risk skoru ve seviyesi belirler.
        
        Ağırlıklı puanlama sistemi:
        - Standart sapma: %40
        - CV: %20
        - Entropi: %20
        - Otokorelasyon: %20
        """
        scores = []

        # Standart Sapma skoru (düşük = riskli)
        if std_deviation < bot_threshold:
            scores.append(1.0)
        elif std_deviation < suspicious_threshold:
            # Lineer interpolasyon
            ratio = (suspicious_threshold - std_deviation) / (suspicious_threshold - bot_threshold)
            scores.append(ratio)
        else:
            scores.append(0.0)

        # CV skoru (düşük = riskli)
        if cv < 0.05:
            scores.append(1.0)
        elif cv < 0.15:
            scores.append((0.15 - cv) / 0.10)
        else:
            scores.append(0.0)

        # Entropi skoru (düşük = riskli)
        if entropy < 0.3:
            scores.append(1.0)
        elif entropy < 0.6:
            scores.append((0.6 - entropy) / 0.3)
        else:
            scores.append(0.0)

        # Otokorelasyon skoru (yüksek = riskli)
        if autocorrelation > 0.8:
            scores.append(1.0)
        elif autocorrelation > 0.5:
            scores.append((autocorrelation - 0.5) / 0.3)
        else:
            scores.append(0.0)

        # Ağırlıklı toplam
        weights = [0.40, 0.20, 0.20, 0.20]
        risk_score = sum(s * w for s, w in zip(scores, weights))
        risk_score = min(max(risk_score, 0.0), 1.0)  # Clamp [0, 1]

        # Risk seviyesi belirleme
        if risk_score >= 0.8:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 0.5:
            risk_level = RiskLevel.SUSPICIOUS
        elif risk_score >= 0.2:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.CLEAN

        return risk_score, risk_level


# Modül seviyesi singleton
statistical_filter = StatisticalFilter()
