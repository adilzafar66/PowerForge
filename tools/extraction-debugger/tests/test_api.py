from unittest.mock import MagicMock
from uuid import uuid4

import app
import pytest
from fastapi.testclient import TestClient
from queries import Attempt

from powerforge_extraction.audit_reader import AuditReadError

SECRET = "local-operator-secret-for-tests"
HEADERS = {"Origin": app.ORIGIN, "X-Debugger-Request": "1"}


@pytest.fixture
def client():
    return TestClient(
        app.create_app(SECRET, object(), object()),
        base_url=app.ORIGIN,
        client=("127.0.0.1", 48000),
    )


def login(client):
    return client.post("/api/login", json={"secret": SECRET}, headers=HEADERS)


def test_loopback_and_host():
    server = app.create_app(SECRET, None, None)
    remote = TestClient(server, base_url=app.ORIGIN, client=("10.0.0.2", 12345))
    assert remote.get("/api/attempts").status_code == 403
    spoof = TestClient(server, base_url="http://evil.invalid", client=("127.0.0.1", 12345))
    assert spoof.get("/").status_code == 403


def test_login_session_csrf_logout(client, monkeypatch):
    assert client.get("/api/attempts").status_code == 401
    assert client.post("/api/login", json={"secret": SECRET}).status_code == 403
    response = login(client)
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=strict" in response.headers["Set-Cookie"]
    assert response.headers["Cache-Control"] == "no-store"
    monkeypatch.setattr(app, "list_attempts", lambda *_a, **_kw: {"items": [], "next_cursor": None})
    assert client.get("/api/attempts").status_code == 200
    assert client.get("/api/attempts?limit=200").status_code == 422
    assert client.get("/api/attempts", headers={"Origin": "http://other"}).status_code == 403
    assert client.post(f"/api/attempts/{uuid4()}/original").status_code == 403
    assert client.post("/api/logout", headers=HEADERS).status_code == 204
    assert client.get("/api/attempts").status_code == 401


@pytest.mark.parametrize(
    "reason,status",
    [("expired", 410), ("not_captured", 404), ("object_missing", 404), ("integrity_failed", 409)],
)
def test_reveal_denials(client, monkeypatch, reason, status):
    def deny(*_args):
        raise AuditReadError(reason)

    monkeypatch.setattr(app, "read_audit", deny)
    assert login(client).status_code == 204
    reply = client.post(f"/api/attempts/{uuid4()}/original", headers=HEADERS)
    assert reply.status_code == status and reply.json() == {"detail": reason}
    assert reply.headers["Cache-Control"] == "no-store"


def test_reveal_uses_shared_reader_without_reserializing(client, monkeypatch):
    original = b'\n {"raw_value":"\xe2\x84\xa6"} \n'
    calls = []
    monkeypatch.setattr(app, "read_audit", lambda engine, store, id: calls.append(id) or original)
    id = uuid4()
    login(client)
    assert client.get(f"/api/attempts/{id}/original").status_code == 405
    reply = client.post(f"/api/attempts/{id}/original", headers=HEADERS)
    assert reply.content == original and calls == [id]


def test_errors_do_not_echo_input(client, monkeypatch, caplog):
    response = client.post("/api/login", json={"secret": {"private": SECRET}}, headers=HEADERS)
    assert response.status_code == 422 and SECRET not in response.text
    login(client)

    def fail(*_args, **_kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(app, "list_attempts", fail)
    response = client.get("/api/attempts")
    assert response.status_code == 503 and SECRET not in response.text + caplog.text


def test_historical_attempt_without_model_lists_and_opens():
    attempt_id = uuid4()
    historical = dict.fromkeys(Attempt.model_fields)
    historical.update(
        attempt_id=attempt_id,
        run_id=uuid4(),
        document="historical.pdf",
        page=1,
        attempt_number=1,
        status="COMPLETED",
        provider="openai",
        request_sha256=None,
        result_sha256=None,
        upstream_sha256=None,
        schema_version=None,
        prompt_version=None,
        rejections=[],
        overflow_indices=[],
        fatal=[],
        validated=None,
        performance=None,
        requested_reasoning_effort=None,
    )
    engine = MagicMock()
    execute = engine.connect.return_value.__enter__.return_value.execute
    listed, detail, candidates = (MagicMock() for _ in range(3))
    listed.mappings.return_value.all.return_value = [historical]
    detail.mappings.return_value.one_or_none.return_value = historical
    candidates.mappings.return_value.all.return_value = []
    execute.side_effect = [listed, detail, candidates]
    with TestClient(
        app.create_app(SECRET, engine, None), base_url=app.ORIGIN, client=("127.0.0.1", 48000)
    ) as client:
        assert login(client).status_code == 204
        reply = client.get("/api/attempts")
        assert reply.status_code == 200
        assert reply.json()["items"][0]["model"] is None
        reply = client.get(f"/api/attempts/{attempt_id}")
        assert reply.status_code == 200
        assert reply.json()["attempt"]["model"] is None


def test_startup_uses_storage_region(monkeypatch):
    settings = {
        "EXTRACTION_DEBUGGER_ENABLED": "1",
        "EXTRACTION_DEBUGGER_SECRET": SECRET,
        "EXTRACTION_RESPONSE_AUDIT_DATABASE_URL": "postgresql+psycopg://test_reader:test@localhost/test",
        "EXTRACTION_RESPONSE_AUDIT_ENDPOINT_URL": "http://127.0.0.1:9010",
        "EXTRACTION_RESPONSE_AUDIT_BUCKET": "test-audit",
        "EXTRACTION_RESPONSE_AUDIT_READ_ACCESS_KEY": "test-reader",
        "EXTRACTION_RESPONSE_AUDIT_READ_SECRET_KEY": "test-storage-secret",
        "S3_REGION": "eu-west-2",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    app.get_settings.cache_clear()
    storage_args = {}
    monkeypatch.setattr(app, "S3ObjectStorage", lambda **kwargs: storage_args.update(kwargs))
    monkeypatch.setattr(app.uvicorn, "run", lambda *_args, **_kwargs: None)
    try:
        app.main()
        assert storage_args["region"] == "eu-west-2"
    finally:
        app.get_settings.cache_clear()
