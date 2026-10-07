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


@pytest.fixture
def ctx(require_db: None, use_storage: Any) -> dict[str, Any]:
    """A fresh project with ACTIVE revision "0" and a clean in-memory storage."""
    from documents_support import make_project, make_revision

    storage = use_storage(InMemoryObjectStorage())
    project_id = make_project()
    revision = make_revision(project_id, "0", activate=True).json()
    return {"project_id": project_id, "revision_id": revision["id"], "storage": storage}
