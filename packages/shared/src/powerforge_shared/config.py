from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
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
    max_processing_pages: int = Field(default=1000, gt=0)

    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated browser origins allowed to call the API.",
    )

    ai_classification_enabled: bool = False
    ai_provider: Literal["fake", "openai"] = "fake"
    ai_classification_model: str = "gpt-6-luna"
    ai_classification_reasoning_effort: str = "none"
    ai_classification_image_detail: str = "low"
    ai_classification_timeout_seconds: int = Field(default=60, gt=0)
    ai_classification_task_soft_time_limit_seconds: int = Field(default=600, gt=0)
    ai_classification_task_hard_time_limit_seconds: int = Field(default=660, gt=0)
    openai_api_key: str | None = None

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("s3_public_endpoint_url", "openai_api_key", mode="before")
    @classmethod
    def blank_string_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def classification_soft_limit_is_below_hard(self) -> Self:
        soft = self.ai_classification_task_soft_time_limit_seconds
        hard = self.ai_classification_task_hard_time_limit_seconds
        if soft >= hard:
            raise ValueError(
                "AI_CLASSIFICATION_TASK_SOFT_TIME_LIMIT_SECONDS must be less than "
                "AI_CLASSIFICATION_TASK_HARD_TIME_LIMIT_SECONDS"
            )
        return self

    def s3_public_endpoint(self) -> str:
        return self.s3_public_endpoint_url or self.s3_endpoint_url

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
