import pytest
from pydantic import ValidationError

from powerforge_shared.config import Settings

PHASE2_ENV_VARS = (
    "S3_ENDPOINT_URL",
    "S3_PUBLIC_ENDPOINT_URL",
    "S3_SIGNED_URL_EXPIRES_SECONDS",
    "MAX_UPLOAD_BYTES",
    "MAX_IMAGE_PIXELS",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in PHASE2_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def fresh_settings() -> Settings:
    return Settings(_env_file=None)


def test_database_url_normalizes_postgres_scheme() -> None:
    settings = Settings(database_url="postgres://user:pass@localhost:5432/powerforge")
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_database_url_normalizes_postgresql_scheme() -> None:
    settings = Settings(database_url="postgresql://user:pass@localhost:5432/powerforge")
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_cors_origin_list_splits_csv() -> None:
    settings = Settings(cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert settings.cors_origin_list() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_phase2_defaults(clean_env: pytest.MonkeyPatch) -> None:
    settings = fresh_settings()
    assert settings.s3_public_endpoint_url is None
    assert settings.s3_signed_url_expires_seconds == 900
    assert settings.max_upload_bytes == 262_144_000
    assert settings.max_image_pixels == 600_000_000


def test_public_endpoint_falls_back_to_internal(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    assert fresh_settings().s3_public_endpoint() == "http://minio:9000"


def test_blank_public_endpoint_falls_back_to_internal(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    clean_env.setenv("S3_PUBLIC_ENDPOINT_URL", "  ")
    settings = fresh_settings()
    assert settings.s3_public_endpoint_url is None
    assert settings.s3_public_endpoint() == "http://minio:9000"


def test_public_endpoint_override(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    clean_env.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    assert fresh_settings().s3_public_endpoint() == "http://localhost:9000"


def test_phase2_env_overrides(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("S3_SIGNED_URL_EXPIRES_SECONDS", "60")
    clean_env.setenv("MAX_UPLOAD_BYTES", "1024")
    clean_env.setenv("MAX_IMAGE_PIXELS", "1000000")
    settings = fresh_settings()
    assert settings.s3_signed_url_expires_seconds == 60
    assert settings.max_upload_bytes == 1024
    assert settings.max_image_pixels == 1_000_000


@pytest.mark.parametrize(
    "field,value",
    [
        ("s3_signed_url_expires_seconds", 0),
        ("s3_signed_url_expires_seconds", 604_801),
        ("max_upload_bytes", 0),
        ("max_image_pixels", -1),
    ],
)
def test_phase2_bounds_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
