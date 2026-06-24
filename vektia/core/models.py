"""
Vektia Data Models

Telemetri olayları, analiz sonuçları ve API yanıtları için
Pydantic veri modelleri. Tüm katmanlar arası veri akışı bu modeller üzerinden yapılır.
"""

from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class ActionType(str, Enum):
    """Oyuncu eylem türleri."""
    HIT = "hit"           # Vurma / saldırı
    CLICK = "click"       # Tıklama (genel)
    MOVE = "move"         # Yürüme / hareket
    TRADE = "trade"       # Ticaret / pazar işlemi
    INTERACT = "interact" # Etkileşim (NPC, nesne)
    CAST = "cast"         # Yetenek kullanımı


class RiskLevel(str, Enum):
    """Risk seviyeleri."""
    CLEAN = "clean"             # Temiz — veri silinir
    LOW = "low"                 # Düşük risk — izlemeye devam
    SUSPICIOUS = "suspicious"   # Şüpheli — ML kuyruğuna ekle
    HIGH = "high"               # Yüksek risk — admin'e bildir
    CONFIRMED = "confirmed"     # Kesin bot — ban kuyruğuna ekle


class BanStatus(str, Enum):
    """Ban durumları."""
    ACTIVE = "active"           # Oyuncu aktif
    FLAGGED = "flagged"         # İşaretlenmiş — admin incelemesi bekliyor
    BANNED = "banned"           # Banlanmış
    WHITELISTED = "whitelisted" # Beyaz listede


# ============================================
# Telemetry Models
# ============================================

class Vector3(BaseModel):
    """3D koordinat vektörü."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class TelemetryEvent(BaseModel):
    """
    Oyun sunucusundan gelen tek bir telemetri olayı.
    Bu, sistemin tükettiği en temel veri birimidir.
    """
    player_id: str = Field(..., min_length=1, max_length=128, description="Oyuncunun benzersiz kimliği")
    client_id: int | None = Field(default=None, description="Müşteri kimliği (API üzerinden doldurulur)")
    action_type: ActionType = Field(..., description="Yapılan eylem türü")
    timestamp: float = Field(..., gt=0, description="Milisaniye cinsinden zaman damgası")
    coords: Vector3 | None = Field(default=None, description="Karakterin anlık X, Y, Z koordinatları")
    server_id: str | None = Field(default=None, max_length=64, description="Kaynak sunucu kimliği")

    model_config = {"json_schema_extra": {
        "example": {
            "player_id": "player_12345",
            "action_type": "hit",
            "timestamp": 1719129600000.0,
            "coords": {"x": 150.5, "y": 200.3, "z": 10.0},
            "server_id": "srv_fivem_01",
        }
    }}


class TelemetryBatch(BaseModel):
    """Toplu telemetri olayları — performans için."""
    events: list[TelemetryEvent] = Field(..., min_length=1, max_length=100)
    server_id: str = Field(..., max_length=64)


# ============================================
# Analysis Results
# ============================================

class WindowData(BaseModel):
    """Katman 1 çıktısı — Sliding Window verisi."""
    client_id: int
    player_id: str
    timestamps: list[float]
    action_type: ActionType
    has_enough_data: bool = False
    window_size: int = 0
    coords_list: list[Vector3 | None] | None = None


class StatsResult(BaseModel):
    """Katman 2 çıktısı — İstatistiksel analiz sonucu."""
    client_id: int
    player_id: str
    std_deviation: float = 0.0
    coefficient_of_variation: float = 0.0
    entropy: float = 0.0
    autocorrelation: float = 0.0
    mean_delta: float = 0.0
    median_delta: float = 0.0
    skewness: float = 0.0
    range_ratio: float = 0.0
    risk_level: RiskLevel = RiskLevel.CLEAN
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def feature_vector(self) -> list[float]:
        """ML modeli için feature vektörü döndürür."""
        return [
            self.std_deviation,
            self.coefficient_of_variation,
            self.entropy,
            self.autocorrelation,
            self.mean_delta,
            self.median_delta,
            self.skewness,
            self.range_ratio,
        ]


class AnalysisResult(BaseModel):
    """Tüm pipeline'ın nihai çıktısı."""
    client_id: int
    player_id: str
    layer: int = Field(..., ge=0, le=3, description="Hangi katmanda tespit edildi")
    risk_level: RiskLevel = RiskLevel.CLEAN
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    std_deviation: float = 0.0
    flagged: bool = False
    details: dict = Field(default_factory=dict)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================
# API Response Models
# ============================================

class HealthResponse(BaseModel):
    """Sağlık kontrolü yanıtı."""
    status: str = "healthy"
    version: str
    redis_connected: bool
    uptime_seconds: float


class TokenResponse(BaseModel):
    """JWT token yanıtı."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PlayerSummary(BaseModel):
    """Oyuncu özet bilgisi."""
    player_id: str
    status: BanStatus = BanStatus.ACTIVE
    risk_level: RiskLevel = RiskLevel.CLEAN
    risk_score: float = 0.0
    total_events: int = 0
    last_seen: datetime | None = None
    flagged_count: int = 0


class AlertEvent(BaseModel):
    """Admin paneline gönderilen uyarı olayı."""
    alert_id: str
    player_id: str
    risk_level: RiskLevel
    risk_score: float
    layer: int
    details: dict
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False


class DashboardStats(BaseModel):
    """Dashboard özet istatistikleri."""
    total_players: int = 0
    active_players: int = 0
    flagged_players: int = 0
    banned_players: int = 0
    events_processed_24h: int = 0
    detection_rate: float = 0.0
    false_positive_rate: float = 0.0
    avg_response_time_ms: float = 0.0
