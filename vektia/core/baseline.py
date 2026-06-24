"""
Vektia Per-Player Baseline & Trust — Faz 3 (Yanlış Pozitif Azaltma)

Global eşikler (layer2) herkese aynı davranır; uzun süredir temiz oynayan gerçek
bir oyuncu (ör. ritmik ama insan) ile yeni/şüpheli bir hesabı ayırmaz. Bu modül
her oyuncu + aksiyon için kendi geçmişine dayalı bir GÜVEN (trust) skoru tutar:

    trust ∈ [0, 1]   — temiz pencerelerin üstel hareketli ortalaması (EMA)

Güven, zamansal kanıt artışını yumuşatan bir LENIENCY çarpanına çevrilir:

    leniency = 1 - baseline_trust_leniency * trust      (∈ [1-α, 1])

Pipeline bu leniency'yi temporal.record()'a geçirir; güvenilen oyuncunun
şüpheli/HIGH pencereleri kanıt skoruna daha az katkı yapar → kesin karara
ulaşmak için daha fazla SÜRDÜRÜLEN kanıt gerekir. Böylece:
  - Kalıcı gerçek oyuncu (yüksek trust): FP'ye karşı ekstra korumalı.
  - Bot / yeni hesap (düşük trust): tam hassasiyette — leniency ≈ 1.0.

EMA kullanılır (kümülatif oran değil) ki hesap ele geçirilirse (insan→makro)
güven yakın geçmişe göre hızla düşsün ve bot yine yakalansın.

Not: Bu yalnızca YUMUŞATMA yapar, sert whitelist DEĞİLDİR. Yeterince sürdürülen
kanıt biriken gerçek bir makro, güvenilen oyuncuda bile (biraz daha geç) yakalanır.
"""

from dataclasses import dataclass

from vektia.core.models import RiskLevel, ActionType
from vektia.db.redis_client import get_redis
from vektia.config import get_settings
from vektia.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrustInfo:
    """Baseline değerlendirmesinin çıktısı."""
    trust: float      # [0,1] — temiz davranış EMA'sı
    leniency: float   # zamansal artışı ölçekleyen çarpan (<= 1.0)
    samples: int      # gözlenen pencere sayısı (min_samples kapısı için)


class PlayerBaseline:
    """
    Oyuncu + aksiyon bazında temiz-pencere EMA'sından güven (trust) üretir.

    Redis anahtarı (hash): vektia:client:{cid}:player:{pid}:{action}:baseline
      alanlar: t (trust EMA, float), n (gözlenen pencere sayısı)
    """

    def _key(self, client_id: int, player_id: str, action_type) -> str:
        action = action_type.value if isinstance(action_type, ActionType) else str(action_type)
        return f"vektia:client:{client_id}:player:{player_id}:{action}:baseline"

    async def observe(
        self,
        client_id: int,
        player_id: str,
        action_type,
        window_risk: RiskLevel,
    ) -> TrustInfo:
        """
        Bir pencerenin riskini güven EMA'sına işler ve güncel leniency'yi döndürür.
        """
        settings = get_settings()
        if not settings.baseline_enabled:
            return TrustInfo(trust=0.0, leniency=1.0, samples=0)

        # Temiz davranış göstergesi: CLEAN/LOW pencere = güven artırıcı (1.0),
        # SUSPICIOUS/HIGH = güven düşürücü (0.0).
        clean_signal = 1.0 if window_risk in (RiskLevel.CLEAN, RiskLevel.LOW) else 0.0

        key = self._key(client_id, player_id, action_type)
        prev_t = 0.0
        n = 0
        redis = None
        try:
            redis = await get_redis()
            vals = await redis.hmget(key, "t", "n")
            if vals[0] is not None:
                prev_t = float(vals[0])
            if vals[1] is not None:
                n = int(vals[1])
        except Exception as e:
            logger.error(f"Baseline okuma hatası: {e}")
            redis = None

        decay = settings.baseline_ema_decay
        t = decay * prev_t + (1.0 - decay) * clean_signal
        t = max(0.0, min(1.0, t))
        n += 1

        if redis is not None:
            try:
                await redis.hset(key, mapping={"t": t, "n": n})
                await redis.expire(key, settings.baseline_ttl_seconds)
            except Exception as e:
                logger.error(f"Baseline yazma hatası: {e}")

        # Yeterli örnek yoksa güveni uygulama (yeni hesap normal hassasiyette kalır).
        if n < settings.baseline_min_samples:
            return TrustInfo(trust=t, leniency=1.0, samples=n)

        leniency = 1.0 - settings.baseline_trust_leniency * t
        leniency = max(0.0, min(1.0, leniency))
        return TrustInfo(trust=t, leniency=leniency, samples=n)

    async def reset(self, client_id: int, player_id: str, action_type=None) -> None:
        """Bir oyuncunun baseline güvenini sıfırlar."""
        try:
            redis = await get_redis()
            if action_type is not None:
                await redis.delete(self._key(client_id, player_id, action_type))
            else:
                for at in ActionType:
                    await redis.delete(self._key(client_id, player_id, at))
        except Exception as e:
            logger.error(f"Baseline reset hatası: {e}")


# Modül seviyesi singleton
player_baseline = PlayerBaseline()
