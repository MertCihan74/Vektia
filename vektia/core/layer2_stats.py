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
import scipy.stats

from vektia.core.models import WindowData, StatsResult, RiskLevel, ActionType
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

        # === Veri Hijyeni ===
        # Kanonik birim: MİLİSANİYE (bkz. TELEMETRY_DATA_FORMAT.md).
        # Sıfır/negatif delta'lar duplicate event'tir; 1ms altı delta'lar ise
        # neredeyse her zaman ağ tekrarı (resend) / batch sıkışması artefaktıdır.
        # Bu artefaktlar varyansı yapay olarak sıfıra çekip GERÇEK OYUNCUYU bot
        # gibi gösterir (yanlış pozitif). Bu yüzden alt sınırla temizliyoruz.
        # Büyük delta'lar (oyuncu molası) bilinçli olarak KORUNUR: insanı bot
        # gibi göstermezler, aksine "insani düzensizlik" sinyalidir.
        MIN_DELTA_MS = 1.0
        deltas = deltas[deltas >= MIN_DELTA_MS]

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

        # 6. Skewness (Çarpıklık) - İnsanlar pozitif çarpıktır (fat tail), botlar simetrik
        skewness = float(scipy.stats.skew(deltas)) if len(deltas) > 2 else 0.0

        # 7. Range Ratio (Max/Min Oranı) - İnsanlarda oran çok büyüktür (>5.0)
        min_delta = float(np.min(deltas))
        max_delta = float(np.max(deltas))
        range_ratio = float(max_delta / min_delta) if min_delta > 0 else 1.0

        # === Risk Değerlendirmesi ===
        risk_score, risk_level = self._evaluate_risk(
            action_type=window_data.action_type,
            coords_list=window_data.coords_list if hasattr(window_data, "coords_list") else None,
            std_deviation=std_deviation,
            cv=cv,
            entropy=entropy,
            autocorrelation=autocorrelation,
            skewness=skewness,
            range_ratio=range_ratio,
            mean_delta=mean_delta,
            median_delta=median_delta,
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
            skewness=skewness,
            range_ratio=range_ratio,
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

    def _calculate_autocorrelation(self, deltas: np.ndarray, max_lag: int = 5) -> float:
        """
        Ardışık delta'lar arası en yüksek otokorelasyonu hesaplar (Gelişmiş Makro Tespiti).

        Gelişmiş makrolar sıralı desenler (örn: [100ms, 200ms, 400ms, 600ms] loop) kullanır.
        Bu tür desenler, desen uzunluğuna denk gelen lag (gecikme) değerinde
        mükemmel korelasyon üretir. Birden fazla lag kontrol edilir.
        """
        if len(deltas) < 3:
            return 0.0

        n = len(deltas)
        mean = np.mean(deltas)
        variance = np.var(deltas)

        if variance == 0:
            return 1.0  # Sıfır varyans = mükemmel korelasyon = kesin bot

        max_ac = 0.0
        # Makro deseninin uzunluğu en fazla max_lag kadar olabilir diye varsayıyoruz.
        limit = min(max_lag, n - 2)

        for lag in range(1, limit + 1):
            autocov = np.sum((deltas[:n - lag] - mean) * (deltas[lag:] - mean)) / n
            ac = autocov / variance
            if abs(ac) > max_ac:
                max_ac = abs(ac)

        return float(max_ac)

    def _spatial_score(self, xs, ys, cv: float, range_ratio: float) -> float:
        """
        Mouse/konum dizisinden ROBOTİK HAREKET sinyali üretir (0=insan .. 1=bot).

        Felsefe: İnsan mouse'u eğrisel, gürültülü, overshoot'ludur; bot düz/sabit/
        öngörülebilir hareket eder. Bu, zamanlamayı (timing) mükemmel taklit eden
        botları FARKLI bir boyutta yakalar — gerçek insan doğal olarak geçer.

        FP-GÜVENLİ: Tek başına ban üretmez; ağırlıklı skora bir sinyal olarak girer
        (temporal + ML hâlâ süzer). Ayrıca İNSANİ hareket (skor 0) risk skorunu
        DÜŞÜRÜR — yani mouse verisi yanlış pozitifi de azaltır.
        """
        xs = np.asarray(xs, dtype=np.float64)
        ys = np.asarray(ys, dtype=np.float64)
        std_x = float(np.std(xs))
        std_y = float(np.std(ys))
        spread = float(np.hypot(std_x, std_y))

        score = 0.0

        # 1) Neredeyse sıfır mekansal yayılım = sabit hedefe oto-tıklama.
        #    Yalnızca ritim de düzenliyse güçlü sinyal (insanın nişan alması korunur).
        if spread < 2.0:
            score = max(score, 0.9 if (cv < 0.15 or range_ratio < 1.20) else 0.35)

        # Ardışık tıklamalar arası hareket vektörleri
        dx = np.diff(xs)
        dy = np.diff(ys)
        dists = np.hypot(dx, dy)
        mask = dists > 1.0           # gerçek hareket olan adımlar (piksel)
        moving = dists[mask]

        if len(moving) >= 4:
            # 2) Adım mesafeleri aşırı düzenli = scriptli/sabit-hızlı hareket
            m = float(np.mean(moving))
            dist_cv = float(np.std(moving) / m) if m > 0 else 0.0
            if dist_cv < 0.08:
                score = max(score, 0.85)
            elif dist_cv < 0.20:
                score = max(score, 0.5)

            # 3) Yol düzlüğü: ardışık yön değişimleri çok küçükse = robotik düz yol.
            #    İnsan zikzak/düzeltme yapar → yüksek açısal sapma.
            angles = np.arctan2(dy[mask], dx[mask])
            dangles = np.diff(angles)
            dangles = (dangles + np.pi) % (2 * np.pi) - np.pi   # [-pi, pi]
            if len(dangles) >= 3:
                ang_std = float(np.std(dangles))
                if ang_std < 0.12:
                    score = max(score, 0.7)

        return float(min(score, 1.0))

    def _evaluate_risk(
        self,
        action_type: ActionType,
        coords_list: list | None,
        std_deviation: float,
        cv: float,
        entropy: float,
        autocorrelation: float,
        skewness: float,
        range_ratio: float,
        mean_delta: float,
        median_delta: float,
        bot_threshold: float,
        suspicious_threshold: float,
    ) -> tuple[float, RiskLevel]:
        """
        Birden fazla metriği birleştirerek nihai risk skoru ve seviyesi belirler.
        """

        # === Mekansal Analiz (Spatial Jitter + robotik hareket) ===
        # has_spatial: koordinat varsa mekansal sinyal ağırlıklı skora dahil edilir.
        # Bot ise skoru yükseltir; İNSAN ise (skor~0) düşürür → FP'yi de azaltır.
        spatial_score = 0.0
        has_spatial = False
        if action_type == ActionType.CLICK and coords_list:
            valid_coords = [c for c in coords_list if c is not None]
            if len(valid_coords) >= 5:
                xs = [c.x for c in valid_coords]
                ys = [c.y for c in valid_coords]
                std_x = float(np.std(xs))
                std_y = float(np.std(ys))
                has_spatial = True
                spatial_score = self._spatial_score(xs, ys, cv, range_ratio)
                # En güçlü kesin durum: hem X hem Y sıfır + kusursuz ritim = Makro.
                # (range_ratio<1.03 / cv<0.05 → tek-pencere HIGH, temporal süzer.)
                if std_x == 0.0 and std_y == 0.0:
                    if cv < 0.05 or range_ratio < 1.03:
                        return 1.0, RiskLevel.HIGH
                    # 0 piksel ama dağınık ritim → pusuda manuel tıklayan insan. Müsade et.

        # === Aksiyon Tipine Göre Tolerans ===
        # Klavye tuşlarına basılı tutulduğunda işletim sistemi mükemmel bir ritimle (örn 30ms) tuşu tekrarlar.
        # Bu yüzden klavye hareketlerinde (MOVE) katı zamanlama kurallarını atlıyoruz.
        # NOT: Tüm zaman eşikleri artık MİLİSANİYE cinsindendir (kanonik birim).
        if action_type == ActionType.MOVE:
            if mean_delta < 8.0:  # 8ms'den hızlı hareketler speedhack/flood olabilir
                return 1.0, RiskLevel.HIGH
            return 0.0, RiskLevel.CLEAN

        # Fare tıklamaları (CLICK vb.) için katı zamanlama kuralları:
        # ÖNEMLİ: Bu kurallar artık tek başına BAN üretmez. Pipeline'daki zamansal
        # biriktirici (temporal.py) bu HIGH sinyallerini birden çok pencerede
        # toplayıp sürdürülen kanıt oluşmadıkça kesin karara dönüştürmez.
        if range_ratio < 1.03:
            # Yalnızca aşırı stabil (<%3 aralık) tıklamalar tek-pencere HIGH üretir.
            # Eşik 1.05'ten 1.03'e indirildi: ritmik insanları yanlış vurmamak için.
            return 1.0, RiskLevel.HIGH

        if mean_delta < 35.0 or median_delta < 35.0:
            # Ortalama veya medyan 35ms altındaysa (>28 CPS) kesinlikle bottur.
            # Gerçek insanlar (drag click dahil) 25-30 CPS'yi geçemez.
            return 1.0, RiskLevel.HIGH

        if mean_delta < 60.0 and cv < 0.10:
            # Çok Hızlı ama Çok Stabil = Makro
            # Saniyede 16+ tıklama yaparken ritmi %10'dan az sapan birisi makrodur.
            # İnsanlar hızlı tıkladıklarında (jitter/drag click) çok yüksek ritim bozukluğu yaşarlar (cv > 0.20).
            return 1.0, RiskLevel.HIGH

        if autocorrelation > 0.80:
            # Otokorelasyon eşiği 0.70'ten 0.80'e yükseltildi. Küçük örneklemde
            # (19 delta) ve çoklu-lag'den "en yükseği seçme" yanlılığı nedeniyle
            # 0.70 insanlarda şans eseri aşılabiliyordu; 0.80 yalnızca gerçek
            # döngüsel makro desenlerini hedefler.
            return 1.0, RiskLevel.HIGH

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
        # Zaten hard threshold (>0.80) ile banlanıyor, ama 0.40 - 0.80 arası şüpheli kabul edilebilir
        if autocorrelation > 0.60:
            scores.append(1.0)
        elif autocorrelation > 0.40:
            scores.append((autocorrelation - 0.40) / 0.20)
        else:
            scores.append(0.0)

        # Skewness skoru (0'a yakın olması simetrik (bot) olduğunu gösterir)
        if abs(skewness) < 0.2:
            scores.append(1.0)
        elif abs(skewness) < 0.8:
            scores.append((0.8 - abs(skewness)) / 0.6)
        else:
            scores.append(0.0)

        # Ağırlıklı toplam
        weights = [0.35, 0.15, 0.15, 0.15, 0.20]

        # Mekansal sinyal (yalnızca CLICK + koordinat varsa). Botta skoru yükseltir,
        # insanda (skor~0) toplam ortalamayı düşürür → hem recall artar hem FP düşer.
        if has_spatial:
            scores = scores + [spatial_score]
            weights = weights + [0.30]

        total_w = sum(weights)
        risk_score = sum(s * w for s, w in zip(scores, weights)) / total_w
        risk_score = min(max(risk_score, 0.0), 1.0)  # Clamp [0, 1]

        # Risk seviyesi belirleme
        if risk_score >= 0.8:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 0.3:  # ML'e daha fazla veri gitmesi için eşik düşürüldü
            risk_level = RiskLevel.SUSPICIOUS
        elif risk_score >= 0.15:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.CLEAN

        return risk_score, risk_level


# Modül seviyesi singleton
statistical_filter = StatisticalFilter()
