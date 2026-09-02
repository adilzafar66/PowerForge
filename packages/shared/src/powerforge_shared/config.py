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

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
