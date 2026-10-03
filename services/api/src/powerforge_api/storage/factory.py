from __future__ import annotations

from functools import lru_cache

from powerforge_api.storage.base import ObjectStorage
from powerforge_api.storage.s3 import S3ObjectStorage
from powerforge_shared.config import Settings, get_settings


def build_s3_storage(settings: Settings) -> S3ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_endpoint(),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
    )


@lru_cache
def get_cached_s3_storage() -> S3ObjectStorage:
    return build_s3_storage(get_settings())


def get_object_storage() -> ObjectStorage:
    """FastAPI dependency. Override with `app.dependency_overrides` in tests."""
    return get_cached_s3_storage()
