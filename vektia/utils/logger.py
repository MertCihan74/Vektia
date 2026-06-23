"""
Vektia Structured Logger

JSON formatında yapılandırılmış loglama. Her log satırı timestamp,
seviye, modül ve bağlam bilgisi içerir.
"""

import logging
import json
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Log kayıtlarını JSON formatında biçimlendirir."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }

        # Ekstra bağlam bilgisi varsa ekle
        if hasattr(record, "player_id"):
            log_data["player_id"] = record.player_id
        if hasattr(record, "layer"):
            log_data["layer"] = record.layer
        if hasattr(record, "risk_score"):
            log_data["risk_score"] = record.risk_score
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        # Exception bilgisi varsa ekle
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Modül bazlı logger oluşturur.

    Args:
        name: Logger adı (genellikle __name__)
        level: Log seviyesi

    Returns:
        Yapılandırılmış Logger instance
    """
    logger = logging.getLogger(f"vektia.{name}")

    # Zaten handler eklenmiş mi kontrol et
    if not logger.handlers:
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        # Üst logger'a propagation'ı kapat (çift log önleme)
        logger.propagate = False

    return logger
