"""Startup behaviour, dependency overrides, and the boto3 import boundary."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from powerforge_api import main
from powerforge_api.storage import InMemoryObjectStorage, ObjectStorage
from powerforge_api.storage.factory import (
    build_s3_storage,
    get_cached_s3_storage,
    get_object_storage,
)
from powerforge_api.storage.s3 import S3ObjectStorage
from powerforge_shared.config import Settings

API_SOURCE = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "powerforge_api"


@pytest.fixture
def quiet_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "configure_logging", lambda _level: None)


def test_startup_check_logs_ready_when_bucket_is_ensured(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = InMemoryObjectStorage()
    monkeypatch.setattr(main, "get_object_storage", lambda: fake)
    with caplog.at_level(logging.INFO, logger="powerforge_api.main"):
        main._ensure_storage_bucket()
    assert fake.calls_for("ensure_bucket") == [None]
    assert any(record.getMessage() == "object storage ready" for record in caplog.records)


def test_startup_check_is_non_fatal_when_storage_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = InMemoryObjectStorage()
    fake.fail_on("ensure_bucket")
    monkeypatch.setattr(main, "get_object_storage", lambda: fake)
    with caplog.at_level(logging.WARNING, logger="powerforge_api.main"):
        main._ensure_storage_bucket()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].__dict__["error_class"] == "StorageError"


def test_startup_check_survives_construction_errors(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode() -> ObjectStorage:
        raise ValueError("Invalid endpoint: not-a-url")

    monkeypatch.setattr(main, "get_object_storage", explode)
    with caplog.at_level(logging.WARNING, logger="powerforge_api.main"):
        main._ensure_storage_bucket()
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "not-a-url" not in " ".join(r.getMessage() for r in caplog.records)


def test_app_boots_and_serves_when_storage_is_down(
    monkeypatch: pytest.MonkeyPatch, quiet_logging: None
) -> None:
    fake = InMemoryObjectStorage()
    fake.fail_on("ensure_bucket")
    monkeypatch.setattr(main, "get_object_storage", lambda: fake)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    assert fake.calls_for("ensure_bucket") == [None]


def test_dependency_override_replaces_real_storage(
    object_storage: InMemoryObjectStorage,
) -> None:
    app = FastAPI()

    @app.get("/probe")
    def probe(storage: Annotated[ObjectStorage, Depends(get_object_storage)]) -> dict[str, bool]:
        return {"is_fake": storage is object_storage}

    app.dependency_overrides.update(main.app.dependency_overrides)
    assert TestClient(app).get("/probe").json() == {"is_fake": True}


def test_default_dependency_is_a_cached_s3_storage() -> None:
    get_cached_s3_storage.cache_clear()
    first = get_object_storage()
    assert isinstance(first, S3ObjectStorage)
    assert get_object_storage() is first
    get_cached_s3_storage.cache_clear()


def test_factory_maps_settings_to_storage() -> None:
    settings = Settings(
        _env_file=None,
        s3_endpoint_url="http://minio:9000",
        s3_public_endpoint_url="http://localhost:9000",
        s3_bucket="custom",
    )
    storage = build_s3_storage(settings)
    assert storage.bucket == "custom"
    url = storage.create_download_url("k", "a.pdf", "application/pdf", "attachment", 60)
    assert url.startswith("http://localhost:9000/custom/k")


def test_only_the_s3_module_imports_boto3() -> None:
    offenders: list[str] = []
    for path in API_SOURCE.rglob("*.py"):
        if path == API_SOURCE / "storage" / "s3.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] in {"boto3", "botocore"} for name in names):
                offenders.append(str(path.relative_to(API_SOURCE)))
    assert offenders == []
