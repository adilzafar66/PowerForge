from collections.abc import Iterator

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
