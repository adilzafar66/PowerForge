import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from powerforge_api.storage import InMemoryObjectStorage


@pytest.fixture
def object_storage() -> Iterator[InMemoryObjectStorage]:
    """Install an in-memory ObjectStorage as the API's storage dependency."""
    from powerforge_api.main import app
    from powerforge_api.storage.factory import get_object_storage

    storage = InMemoryObjectStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_object_storage, None)


@pytest.fixture
def require_db() -> None:
    from sqlalchemy import text

    from powerforge_api.db import get_engine, get_session_factory

    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


@pytest.fixture
def use_storage() -> Iterator[Callable[[InMemoryObjectStorage], InMemoryObjectStorage]]:
    """Install an in-memory storage as the API's storage dependency; callable repeatedly."""
    from powerforge_api.main import app
    from powerforge_api.storage.factory import get_object_storage

    def install(storage: InMemoryObjectStorage) -> InMemoryObjectStorage:
        app.dependency_overrides[get_object_storage] = lambda: storage
        return storage

    yield install
    app.dependency_overrides.pop(get_object_storage, None)


@pytest.fixture(scope="session")
def s3_scratch_storage() -> Iterator[Any]:
    """A real S3ObjectStorage on a throwaway bucket (integration; needs MinIO).

    When MinIO is unreachable this skips locally and fails under CI, so a broken CI
    service cannot hide behind a silent skip.
    """
    import uuid

    from powerforge_api.storage import StorageError
    from powerforge_api.storage.s3 import S3ObjectStorage
    from powerforge_shared.config import get_settings

    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live storage tests.")
    settings = get_settings()
    storage = S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_endpoint(),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=f"powerforge-test-{uuid.uuid4().hex[:10]}",
        region=settings.s3_region,
    )
    try:
        storage.ensure_bucket()
    except StorageError as exc:
        message = f"Object storage is not reachable at {settings.s3_endpoint_url}"
        if os.environ.get("CI"):
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
        raise AssertionError from exc
    try:
        yield storage
    finally:
        client = storage._client
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=storage.bucket):
            for item in page.get("Contents", []):
                client.delete_object(Bucket=storage.bucket, Key=item["Key"])
        client.delete_bucket(Bucket=storage.bucket)


@pytest.fixture
def ctx(require_db: None, use_storage: Any) -> dict[str, Any]:
    """A fresh project with ACTIVE revision "0" and a clean in-memory storage."""
    from documents_support import make_project, make_revision

    storage = use_storage(InMemoryObjectStorage())
    project_id = make_project()
    revision = make_revision(project_id, "0", activate=True).json()
    return {"project_id": project_id, "revision_id": revision["id"], "storage": storage}
