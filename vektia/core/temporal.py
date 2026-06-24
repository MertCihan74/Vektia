"""
Vektia Temporal Evidence Aggregator — Faz 1 (Yanlış Pozitif Azaltma)

Tek bir telemetri penceresi (varsayılan 20 tıklama) istatistiksel olarak küçük
bir örneklemdir. Tek bir pencereye bakıp oyuncuyu "bot" ilan etmek, gerçek
oyuncularda yüksek yanlış pozitif üretir (şanssız bir ritim, ağ artefaktı vb.).

Bu modül, Katman 2'nin pencere-bazlı risk sinyallerini ZAMAN İÇİNDE biriktirir
ve kesin karara (CONFIRMED) ancak SÜRDÜRÜLEN kanıt oluştuğunda izin verir.

Mekanizma — söndürmeli (decay) kanıt skoru:

    yeni_skor = decay * eski_skor + artış(pencere_riski)

  - HIGH pencere       → +high_increment       (varsayılan 1.0)
  - SUSPICIOUS pencere → +suspicious_increment (varsayılan 0.4)
  - CLEAN / LOW        → artış yok (skor yalnızca decay ile söner)

Varsayılan parametrelerle (decay=0.6, high_inc=1.0, confirm=1.9):
  - İzole tek bir HIGH penceresi: skor 1.0 → yalnızca "şüpheli", ASLA confirm.
    Sonraki temiz pencerelerde 0.6 → 0.36 → ... hızla söner.
  - Gerçek bir makro her pencerede HIGH ürettiği için ~3 ardışık pencerede
    skor confirm eşiğini aşar (1.0 → 1.6 → 1.96 ≥ 1.9).
  - HIGH akışının kanıt asimptotu high_inc/(1-decay)=2.5'tir; confirm eşiği bunun
    ALTINDA (1.9) olmalı, yoksa hiç aşılmaz. SUSPICIOUS-only akış asimptotu ise
    0.4/0.4=1.0 < 1.9 olduğundan SUSPICIOUS tek başına asla confirm üretmez.

Kayan pencere üst üste bindiği için (her yeni tıklama son N'i yeniden analiz
eder), tek bir insani/düzensiz tıklama pencereyi anında CLEAN'e çevirip kanıt
zincirini kırar — bu da insan oyuncuyu doğal olarak korur.
"""

from dataclasses import dataclass

from vektia.core.models import RiskLevel, ActionType
from vektia.db.redis_client import get_redis
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TemporalDecision:
    """Zamansal biriktiricinin nihai kararı."""
    evidence: float          # birikmiş kanıt skoru
    tier: RiskLevel          # zamansal karar: CLEAN / SUSPICIOUS / CONFIRMED
    window_risk: RiskLevel   # bu pencerenin ham (anlık) riski
    sustained: bool          # confirm eşiği aşıldı mı (kesin karara izin)


class SuspicionTracker:
    """
    Oyuncu + aksiyon tipi bazında zamansal şüphe kanıtını Redis'te yönetir.

    Anahtar: vektia:client:{cid}:player:{pid}:{action}:suspicion
    """

    def _key(self, client_id: int, player_id: str, action_type) -> str:
        action = action_type.value if isinstance(action_type, ActionType) else str(action_type)
        return f"vektia:client:{client_id}:player:{player_id}:{action}:suspicion"

    async def record(
        self,
        client_id: int,
        player_id: str,
        action_type,
        window_risk: RiskLevel,
        leniency: float = 1.0,
    ) -> TemporalDecision:
        """
        Bir pencerenin risk sonucunu kanıt skoruna işler ve zamansal karar üretir.

        Args:
            leniency: Kanıt artışını ölçekleyen çarpan (Faz 3 — per-player baseline).
                1.0 = normal hassasiyet (varsayılan). <1.0 = güvenilen oyuncu;
                şüpheli pencereler kanıta daha az katkı yapar, confirm için daha
                fazla sürdürülen kanıt gerekir. Söndürme (decay) etkilenmez.
        """
        settings = get_settings()

        # Zamansal katman kapalıysa: eski (tek-pencere) davranışa düş.
        if not settings.temporal_enabled:
            sustained = window_risk in (RiskLevel.HIGH, RiskLevel.CONFIRMED)
            tier = RiskLevel.CONFIRMED if sustained else window_risk
            return TemporalDecision(
                evidence=0.0, tier=tier, window_risk=window_risk, sustained=sustained
            )

        # Pencere riskine göre artış miktarı
        if window_risk in (RiskLevel.HIGH, RiskLevel.CONFIRMED):
            inc = settings.temporal_high_increment
        elif window_risk == RiskLevel.SUSPICIOUS:
            inc = settings.temporal_suspicious_increment
        else:
            inc = 0.0  # CLEAN / LOW → yalnızca söner

        # Faz 3: güvenilen oyuncuda artışı yumuşat (söndürmeyi değil, yalnızca artışı).
        inc *= max(0.0, min(1.0, leniency))

        redis = None
        key = self._key(client_id, player_id, action_type)
        prev = 0.0
        try:
            redis = await get_redis()
            raw = await redis.get(key)
            if raw is not None:
                prev = float(raw)
        except Exception as e:
            logger.error(f"Temporal okuma hatası: {e}")
            redis = None

        evidence = settings.temporal_decay_factor * prev + inc
        if evidence < 0.0:
            evidence = 0.0

        # Kanıtı kalıcılaştır (TTL ile — inaktif oyuncuda otomatik temizlenir)
        if redis is not None:
            try:
                await redis.set(key, evidence, ex=settings.temporal_ttl_seconds)
            except Exception as e:
                logger.error(f"Temporal yazma hatası: {e}")

        # Zamansal karar
        if evidence >= settings.temporal_confirm_threshold:
            tier = RiskLevel.CONFIRMED
            sustained = True
        elif evidence >= settings.temporal_suspect_threshold:
            tier = RiskLevel.SUSPICIOUS
            sustained = False
        else:
            # Yeterli kanıt yok → temiz say, sadece izlemeye devam et.
            tier = RiskLevel.CLEAN
            sustained = False

        return TemporalDecision(
            evidence=evidence, tier=tier, window_risk=window_risk, sustained=sustained
        )

    async def reset(self, client_id: int, player_id: str, action_type=None) -> None:
        """Bir oyuncunun kanıt skorunu sıfırlar (whitelist / manuel temizleme)."""
        try:
            redis = await get_redis()
            if action_type is not None:
                await redis.delete(self._key(client_id, player_id, action_type))
            else:
                for at in ActionType:
                    await redis.delete(self._key(client_id, player_id, at))
        except Exception as e:
            logger.error(f"Temporal reset hatası: {e}")


# Modül seviyesi singleton
suspicion_tracker = SuspicionTracker()
