"""
Vektia Bot & İnsan Simülasyonu

Farklı oyuncu profilleriyle sistemi test eder:
- Bot profilleri: Sabit ritim, rastgele gecikmeli bot, gelişmiş makro
- İnsan profilleri: Rahat oyuncu, stresli oyuncu, profesyonel oyuncu

Kullanım:
    python scripts/simulate.py
"""

import random
import time
import sys
import os
import io

# Windows cp1254 encoding fix — force UTF-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vektia.core.models import TelemetryEvent, ActionType, WindowData
from vektia.core.layer2_stats import StatisticalFilter


def generate_bot_clicks(count: int = 22, interval_ms: float = 100.0, jitter_ms: float = 1.0) -> list[float]:
    """
    Bot tiklama zamanlari uretir.
    Cok dusuk jitter -- neredeyse mukemmel ritim.
    """
    timestamps = []
    t = time.time() * 1000
    for _ in range(count):
        t += interval_ms + random.uniform(-jitter_ms, jitter_ms)
        timestamps.append(t)
    return timestamps


def generate_macro_clicks(count: int = 22, base_interval_ms: float = 100.0) -> list[float]:
    """
    Gelismis makro tiklamalari -- rastgele gecikme eklenmis ama otokorelasyonu yuksek.
    """
    timestamps = []
    t = time.time() * 1000
    pattern = [100, 105, 98, 102, 100]  # Tekrarlayan desen
    for i in range(count):
        delay = pattern[i % len(pattern)] + random.uniform(-2, 2)
        t += delay
        timestamps.append(t)
    return timestamps


def generate_human_clicks(count: int = 22, profile: str = "casual") -> list[float]:
    """
    Insan tiklama zamanlari uretir.
    Kaotik, biyolojik dalgalanmali -- yuksek standart sapma.
    """
    timestamps = []
    t = time.time() * 1000

    profiles = {
        "casual": (80, 180, 20),     # Rahat oyuncu: genis aralik
        "stressed": (50, 130, 15),   # Stresli: hizli ama duzensiz
        "pro": (60, 120, 10),        # Profesyonel: dar aralik ama hala kaotik
    }

    low, high, fatigue_factor = profiles.get(profile, profiles["casual"])

    for i in range(count):
        # Yorulma etkisi -- zaman gectikce yavasla
        fatigue = (i / count) * fatigue_factor
        delay = random.uniform(low + fatigue, high + fatigue)

        # Dikkat dagilmasi -- %10 ihtimalle ani gecikme
        if random.random() < 0.1:
            delay += random.uniform(50, 200)

        t += delay
        timestamps.append(t)

    return timestamps


def analyze_timestamps(name: str, timestamps: list[float]) -> dict:
    """Timestamp listesini Katman 2 ile analiz eder."""
    stats_filter = StatisticalFilter()

    window = WindowData(
        player_id=name,
        timestamps=timestamps,
        action_type=ActionType.HIT,
        has_enough_data=True,
        window_size=len(timestamps),
    )

    result = stats_filter.analyze(window)

    return {
        "name": name,
        "std_deviation": result.std_deviation,
        "cv": result.coefficient_of_variation,
        "entropy": result.entropy,
        "autocorrelation": result.autocorrelation,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level.value,
        "mean_delta": result.mean_delta,
    }


def main():
    print("=" * 70)
    print("  VEKTIA -- Bot & Insan Simulasyonu")
    print("  Katman 2: Istatistiksel Standart Sapma Analizi")
    print("=" * 70)
    print()

    # === Profiller ===
    profiles = [
        # Bot profilleri
        ("[BOT] Sabit Bot (0ms jitter)", generate_bot_clicks(22, 100, 0.5)),
        ("[BOT] Hafif Jitter Bot (2ms)", generate_bot_clicks(22, 100, 2.0)),
        ("[BOT] Gelismis Makro", generate_macro_clicks(22, 100)),

        # Insan profilleri
        ("[INSAN] Rahat Oyuncu", generate_human_clicks(22, "casual")),
        ("[INSAN] Stresli Oyuncu", generate_human_clicks(22, "stressed")),
        ("[INSAN] Profesyonel Oyuncu", generate_human_clicks(22, "pro")),
    ]

    # === Analiz ===
    results = []
    for name, timestamps in profiles:
        result = analyze_timestamps(name, timestamps)
        results.append(result)

    # === Sonuclar Tablosu ===
    print(f"{'Profil':<32} {'STD Sapma':>12} {'CV':>8} {'Entropi':>8} {'Otokor.':>8} {'Risk':>8} {'Seviye':>12}")
    print("-" * 100)

    for r in results:
        level_marker = {
            "clean": "[OK]", "low": "[LOW]", "suspicious": "[!?]",
            "high": "[!!]", "confirmed": "[XX]"
        }

        print(
            f"{r['name']:<32} "
            f"{r['std_deviation']:>12.6f} "
            f"{r['cv']:>8.4f} "
            f"{r['entropy']:>8.4f} "
            f"{r['autocorrelation']:>8.4f} "
            f"{r['risk_score']:>8.2f} "
            f"{level_marker.get(r['risk_level'], '[??]'):>5} {r['risk_level']:>10}"
        )

    print()
    print("=" * 70)
    print("  YORUM:")
    print("  * STD Sapma < 0.005  -> Bot/Makro (cok dusuk kaotiklik)")
    print("  * STD Sapma > 0.020  -> Insan (dogal biyolojik dalgalanma)")
    print("  * CV (Degisim Katsayisi) dusuk -> ritmik tekrar (bot suphesi)")
    print("  * Entropi dusuk -> duzenli desen (bot suphesi)")
    print("  * Otokorelasyon yuksek -> tekrarlayan pattern (makro suphesi)")
    print("=" * 70)

    # === Dogruluk Kontrolu ===
    print()
    bot_correct = sum(1 for r in results[:3] if r["risk_level"] in ("suspicious", "high", "confirmed", "low"))
    human_correct = sum(1 for r in results[3:] if r["risk_level"] in ("clean", "low"))
    total = len(results)

    print(f"  [SONUC] Bot tespiti: {bot_correct}/3 (risk>0), Insan tespiti: {human_correct}/3 (temiz)")
    print(f"  [SONUC] Genel basari: {bot_correct + human_correct}/{total} ({(bot_correct + human_correct) / total * 100:.0f}%)")


if __name__ == "__main__":
    main()
