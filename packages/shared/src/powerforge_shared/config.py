from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for API and workers. Loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "powerforge-api"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://powerforge:powerforge@localhost:5432/powerforge"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "powerforge"
    s3_secret_key: str = "powerforge_minio"
    s3_bucket: str = "powerforge"
    s3_region: str = "us-east-1"
    s3_public_endpoint_url: str | None = Field(
        default=None,
        description=(
            "Endpoint browsers can reach; presigned download URLs are signed against it. "
            "Falls back to s3_endpoint_url when unset."
        ),
    )
    s3_signed_url_expires_seconds: int = Field(default=900, ge=1, le=604_800)

    max_upload_bytes: int = Field(default=262_144_000, gt=0)
    max_image_pixels: int = Field(default=600_000_000, gt=0)

    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated browser origins allowed to call the API.",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("s3_public_endpoint_url", mode="before")
    @classmethod
    def blank_public_endpoint_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def s3_public_endpoint(self) -> str:
        return self.s3_public_endpoint_url or self.s3_endpoint_url

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
