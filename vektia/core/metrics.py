"""
Vektia Metrics — Faz 4 (Ölçüm & Kalibrasyon)

Saf (yan etkisiz) metrik hesaplayıcıları. Bilinçli olarak sqlalchemy/redis
bağımlılığı YOKTUR; ham sayılar repositories/pipeline tarafından sağlanır.
Böylece kolayca birim test edilir (bkz. tests/test_metrics.py).
"""


def false_positive_rate(flagged: int, banned: int, whitelisted: int) -> float:
    """
    Yanlış-pozitif oranı.

    Tanım: Sistemin aksiyon aldığı (flag/ban/whitelist) oyuncular içinde, admin'in
    "yanlış işaretlendi" diye geri çevirdiklerinin (whitelist) payı. ∈ [0, 1].
    Düşük olması hedef. Hiç aksiyon yoksa 0.0.

    Not: Bu bir proxy'dir — whitelist hem reaktif FP düzeltmesini hem proaktif
    güven listesini kapsar. Daha kesin ölçüm için flagged→whitelisted geçişini
    ayrıca saymak gerekir (sonraki iyileştirme).
    """
    f = max(0, flagged or 0)
    b = max(0, banned or 0)
    w = max(0, whitelisted or 0)
    acted = f + b + w
    if acted <= 0:
        return 0.0
    return round(w / acted, 4)


def shadow_flag_rate(would_flag: int, total_events: int) -> float:
    """
    Shadow modda flag'lenecek pencerelerin tüm olaylara oranı (gözlem amaçlı).
    Yeni eşiklerin canlı flag yükünü, gerçek aksiyon almadan tahmin etmek için.
    """
    t = max(0, total_events or 0)
    if t <= 0:
        return 0.0
    return round(max(0, would_flag or 0) / t, 4)
