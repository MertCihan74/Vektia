"""
API & Pipeline Testleri

FastAPI üzerinden telemetri veri alımının (HTTP POST) ve pipeline'ın
başarıyla çalışıp çalışmadığını test eder.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from vektia.main import app
from vektia.config import get_settings

# Redis ve Veritabanı başlatma/kapatma işlemlerini mockla
# Böylece testler gerçek bir Redis veya veritabanı gerektirmeden çalışır.
@pytest.fixture(autouse=True)
def mock_external_services():
    with patch("vektia.main.init_redis", new_callable=AsyncMock), \
         patch("vektia.main.close_redis", new_callable=AsyncMock), \
         patch("vektia.main.init_database", new_callable=AsyncMock), \
         patch("vektia.main.close_database", new_callable=AsyncMock), \
         patch("vektia.main._ml_worker_background"):
        yield


@pytest.fixture
def client():
    # Lifespan olaylarının mock'lanmış haliyle tetiklenmesi için with bloğu kullanıyoruz
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers():
    settings = get_settings()
    # Test ortamı için geçerli bir token oluşturmak yerine,
    # X-Vektia-Key telemetri endpointinde statik anahtar ile çalışır
    return {"X-Vektia-Key": settings.master_api_key}


class TestTelemetryAPI:

    def test_single_event_unauthorized(self, client):
        """Geçersiz API anahtarı ile istek atıldığında 403 dönmeli."""
        response = client.post(
            "/api/v1/telemetry/event",
            json={
                "player_id": "test_player",
                "action_type": "hit",
                "timestamp": 123456789.0
            },
            headers={"X-Vektia-Key": "invalid_key"}
        )
        assert response.status_code == 403

    @patch("vektia.api.routes.telemetry.process_event", new_callable=AsyncMock)
    def test_single_event_success(self, mock_process_event, client, auth_headers):
        """Geçerli veri ile başarılı bir olay gönderimi."""
        # AsyncMock returns an AnalysisResult-like dict automatically when mocked
        mock_process_event.return_value = {
            "player_id": "test_player",
            "layer": 2,
            "risk_score": 0.0,
            "risk_level": "clean",
            "action": "none",
            "message": "Processed successfully"
        }
        
        response = client.post(
            "/api/v1/telemetry/event",
            json={
                "player_id": "test_player",
                "action_type": "hit",
                "timestamp": 123456789.0
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["player_id"] == "test_player"
        # process_event'in bir kez çağrıldığını doğrula
        mock_process_event.assert_called_once()

    @patch("vektia.api.routes.telemetry.process_event", new_callable=AsyncMock)
    def test_batch_event_success(self, mock_process_event, client, auth_headers):
        """Toplu veri (batch) gönderimi başarılı olmalı."""
        mock_process_event.return_value = {
            "player_id": "p1",
            "layer": 2,
            "risk_score": 0.0,
            "risk_level": "clean",
            "action": "none",
            "message": "Processed"
        }
        
        events = [
            {"player_id": "p1", "action_type": "hit", "timestamp": 100.0},
            {"player_id": "p1", "action_type": "hit", "timestamp": 150.0},
        ]
        
        response = client.post(
            "/api/v1/telemetry/batch",
            json={
                "events": events,
                "server_id": "test_server"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert len(response.json()) == 2
        # process_event 2 kez çağrılmalı
        assert mock_process_event.call_count == 2
