from unittest.mock import patch

from fastapi.testclient import TestClient

from powerforge_api.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "powerforge-api"
    assert "version" in body


def test_api_health_alias() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@patch("powerforge_api.routers.health.database_ready", return_value=True)
@patch("powerforge_api.routers.health.redis_ready", return_value=True)
def test_ready_ok(_redis: object, _database: object) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"


@patch("powerforge_api.routers.health.database_ready", return_value=True)
@patch("powerforge_api.routers.health.redis_ready", return_value=False)
def test_ready_degraded_without_redis(_redis: object, _database: object) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "ok"
    assert body["redis"] == "unavailable"


@patch("powerforge_api.routers.health.database_ready", return_value=False)
@patch("powerforge_api.routers.health.redis_ready", return_value=True)
def test_ready_unavailable_without_database(_redis: object, _database: object) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unavailable"
