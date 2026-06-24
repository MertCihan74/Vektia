"""
Vektia Offline FP/FN Değerlendirme Harness'i (sunucu gerektirmez)

run_ml_experiment.py canlı API'ye yük basar (server + redis + db ister).
Bu script ise tamamen OFFLINE çalışır: sentetik insan + 4 bot profilini
doğrudan Layer 2 (istatistik) → Layer 3 (ML) hattından geçirir ve bir
karışıklık tablosu (confusion matrix) üretir.

ÖNEMLİ: Tüm zaman birimleri MİLİSANİYE (kanonik birim).

Not: Bu ölçüm temporal (L2.5) katmanını İÇERMEZ. Temporal, tek-pencere
kararını birden çok pencerede sürdürülen kanıta bağlayarak FP'yi DAHA DA
düşürür. Yani buradaki insan-FP oranı, gerçek uçtan-uca sistemin ÜST SINIRIDIR
(gerçekte daha düşük olur).
"""

import numpy as np
import random
from datetime import datetime, timezone
from collections import Counter

from vektia.core.models import ActionType, WindowData, RiskLevel
from vektia.core.layer2_stats import statistical_filter
from vektia.core.layer3_ml import ml_detector

EVENTS = 25


# ---------- Profil üreticiler (hepsi MİLİSANİYE) ----------

def human():
    d = np.random.lognormal(mean=np.log(250.0), sigma=0.4, size=EVENTS)
    for i in range(EVENTS):
        if random.random() < 0.10:
            d[i] += random.uniform(1000.0, 5000.0)  # insani duraksama
    return np.clip(d, 100.0, 10000.0)

def naive_bot():
    return np.clip(50.0 + np.random.uniform(-1.0, 1.0, EVENTS), 1.0, None)

def advanced_bot():
    return np.clip(100.0 + np.random.uniform(-20.0, 20.0, EVENTS), 1.0, None)

def very_advanced_bot():
    d = np.random.lognormal(mean=np.log(120.0), sigma=0.2, size=EVENTS)
    if random.random() < 0.3:
        d[random.randint(0, EVENTS - 1)] += random.uniform(1000.0, 3000.0)
    return np.clip(d, 50.0, 5000.0)

def ultimate_ai_bot():
    # AR(1) log-normal: insanın otokorelasyon + kuyruk yapısını taklit eder
    rho, mu, sigma = 0.3, np.log(250.0), 0.4
    out, prev = [], np.random.normal(mu, sigma)
    for _ in range(EVENTS):
        noise = np.random.normal(0, sigma * np.sqrt(1 - rho ** 2))
        val = mu + rho * (prev - mu) + noise
        prev = val
        out.append(np.exp(val))
    return np.clip(np.array(out), 155.0, 5000.0)


PROFILES = {
    "HUMAN":            (human,            "human"),
    "bot_naive":        (naive_bot,        "bot"),
    "bot_advanced":     (advanced_bot,     "bot"),
    "bot_very_advanced":(very_advanced_bot,"bot"),
    "bot_ultimate_ai":  (ultimate_ai_bot,  "bot"),
}


def deltas_to_window(deltas):
    ts, t = [], datetime.now(timezone.utc).timestamp() * 1000.0
    for d in deltas:
        t += float(d)
        ts.append(t)
    return WindowData(
        client_id=1, player_id="eval", timestamps=ts,
        action_type=ActionType.CLICK, has_enough_data=True, window_size=len(ts),
    )


def classify(deltas):
    """Tek pencereyi L2 → L3'ten geçirip nihai risk seviyesini döndürür."""
    sr = statistical_filter.analyze(deltas_to_window(deltas))
    _, level = ml_detector.predict(sr)   # ML güvenlik ağı (eğitilmiş modeli kullanır)
    return level


def main(n=400, seed=42):
    random.seed(seed); np.random.seed(seed)
    print(f"ML eğitilmiş mi: {ml_detector.is_trained}\n")
    print(f"{'Profil':20s} | {'CLEAN':>6s} {'LOW':>5s} {'SUSP':>5s} {'HIGH':>5s} {'CONF':>5s} | sonuç")
    print("-" * 78)

    # İki ayrı metrik:
    #  - FLAG  = SUSPICIOUS+HIGH+CONFIRMED → incelemeye/ML'e gider (oto-aksiyon YOK)
    #  - CONF  = yalnızca CONFIRMED       → oto-aksiyona aday (en kritik metrik)
    human_flag = human_conf = 0
    bot_total = bot_flag = bot_conf = 0
    for name, (gen, truth) in PROFILES.items():
        c = Counter()
        for _ in range(n):
            c[classify(gen()).value] += 1
        flag = c["suspicious"] + c["high"] + c["confirmed"]
        conf = c["confirmed"]
        if truth == "human":
            human_flag, human_conf = flag, conf
            verdict = f"FP-flag={flag/n*100:4.1f}%  FP-confirm={conf/n*100:4.1f}%  (0 hedef)"
        else:
            bot_total += n; bot_flag += flag; bot_conf += conf
            verdict = f"flag={flag/n*100:5.1f}%  confirm={conf/n*100:5.1f}%"
        print(f"{name:20s} | {c['clean']:6d} {c['low']:5d} {c['suspicious']:5d} "
              f"{c['high']:5d} {c['confirmed']:5d} | {verdict}")

    print("-" * 78)
    print(f"İNSAN  : FP-flag={human_flag/n*100:.1f}%  FP-confirm(oto-aksiyon)={human_conf/n*100:.1f}%  "
          f"(tek pencere, temporal HARİÇ → gerçek sistemde daha düşük)")
    print(f"BOT    : flag={bot_flag/bot_total*100:.1f}%  confirm={bot_conf/bot_total*100:.1f}%  "
          f"(flag=incelemeye gider, confirm=oto-aksiyona aday)")


if __name__ == "__main__":
    main()
