import asyncio
import numpy as np
import random
from datetime import datetime, timezone
from vektia.core.models import ActionType, WindowData, RiskLevel
from vektia.core.layer2_stats import statistical_filter
from vektia.core.layer3_ml import ml_detector
from vektia.utils.logger import get_logger

logger = get_logger("train_model")

def simulate_human_clicks(count=25):
    """
    İnsani log-normal dağılımına uygun tıklama aralıkları oluşturur.
    Ortalama 250ms civarı.

    ÖNEMLİ: Birim = MİLİSANİYE (kanonik birim, bkz. TELEMETRY_DATA_FORMAT.md ve
    layer2_stats.MIN_DELTA_MS). Eskiden bu fonksiyon SANİYE üretiyordu; Layer 2
    ms beklediği için tüm insani delta'lar (~0.25) MIN_DELTA_MS=1.0 ile elenip
    feature_vector tamamen SIFIR çıkıyordu → model çöp veriyle eğitiliyordu.
    """
    deltas = np.random.lognormal(mean=np.log(250.0), sigma=0.4, size=count)  # ms

    # İnsani dalgınlık / uzun süre ekrana bakma anları (1–5 sn = 1000–5000 ms)
    for i in range(count):
        if random.random() < 0.1:
            deltas[i] += random.uniform(1000.0, 5000.0)

    return np.clip(deltas, 100.0, 10000.0)  # 100ms altı pek insan için mümkün değil

async def generate_clean_data(num_samples=10000):
    """10,000 insan profili oluşturup StatsResult'larını döndürür."""
    clean_data = []
    
    for i in range(num_samples):
        deltas = simulate_human_clicks(25)
        
        # WindowData oluştur — timestamp'ler MİLİSANİYE cinsinden (kanonik birim)
        timestamps = []
        current_time = datetime.now(timezone.utc).timestamp() * 1000.0  # ms
        for d in deltas:
            current_time += d  # d zaten ms
            timestamps.append(current_time)
            
        wd = WindowData(
            client_id=1,
            player_id=f"train_human_{i}",
            timestamps=timestamps,
            action_type=ActionType.CLICK,
            has_enough_data=True,
            window_size=25
        )
        
        # Layer 2 üzerinden analiz yap (bu bize StatsResult verecek)
        # Sadece istatistiksel analiz yapacağız, ML modeline gitmeyecek
        stats_result = statistical_filter.analyze(wd)
        
        # Filtereden tamamen geçen temiz oyuncuları dahil et
        if stats_result.risk_level in (RiskLevel.CLEAN, RiskLevel.LOW):
            clean_data.append(stats_result)
            
    return clean_data

async def main():
    logger.info("Temiz insan verisi oluşturuluyor...")
    clean_data = await generate_clean_data(10000)
    logger.info(f"{len(clean_data)} adet temiz profil oluşturuldu.")
    
    logger.info("Isolation Forest (Layer 3) ML Modeli yeniden eğitiliyor...")
    # Model'e train ver
    ml_detector.train(clean_data)
    logger.info("Eğitim tamamlandı! Model dosyası yenilendi.")

if __name__ == "__main__":
    asyncio.run(main())
