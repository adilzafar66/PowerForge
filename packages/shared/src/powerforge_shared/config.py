from decimal import Decimal
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
    openai_api_key: str | None = Field(default=None, repr=False)

    enrichment_enabled: bool = False
    enrichment_ocr_configuration: str | None = None
    enrichment_max_concurrent_global: int = Field(default=1, ge=1, le=8)
    enrichment_tesseract_binary: str = "/usr/bin/tesseract"
    enrichment_tessdata_directory: str = "/usr/share/tesseract-ocr/5/tessdata"
    enrichment_worker_only: bool = False

    extraction_enabled: bool = True
    extraction_external_enabled: bool = False
    extraction_operation_semantic_profiles: bool = False
    extraction_model: str = "gpt-6-luna"
    extraction_max_pages: int = Field(default=50, ge=1, le=1000)
    extraction_max_input_bytes: int = Field(default=2_000_000, ge=1, le=16_000_000)
    extraction_max_image_pixels: int = Field(default=20_000_000, ge=1)
    extraction_operation_max_documents: int = Field(default=20, ge=1, le=50)
    extraction_operation_max_pages: int = Field(default=150, ge=1, le=500)
    extraction_operation_max_provider_admissions: int = Field(default=1800, ge=1, le=10000)
    extraction_operation_max_ocr_attempts: int = Field(default=450, ge=1, le=1500)
    extraction_operation_max_concurrent_documents: int = Field(default=2, ge=1, le=10)
    extraction_max_document_bytes: int = Field(default=262_144_000, ge=1)
    extraction_max_output_tokens: int = Field(default=1024, ge=16, le=32768)
    extraction_engineering_max_output_tokens: int = Field(default=16384, ge=16, le=32768)
    extraction_engineering_max_total_input_bytes: int = Field(
        default=4 * 1024 * 1024, ge=1, le=32_000_000
    )
    extraction_engineering_max_text_chars: int = Field(default=100000, ge=1, le=1_000_000)
    extraction_engineering_max_upstream_bytes: int = Field(default=65536, ge=1, le=131072)
    extraction_engineering_image_detail: Literal["high", "auto"] = "high"
    extraction_engineering_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    extraction_tables_max_output_tokens: int = Field(default=32768, ge=16, le=32768)
    extraction_tables_max_total_input_bytes: int = Field(
        default=4 * 1024 * 1024, ge=1, le=32_000_000
    )
    extraction_tables_max_text_chars: int = Field(default=100000, ge=1, le=1_000_000)
    extraction_tables_max_upstream_bytes: int = Field(default=131072, ge=1, le=131072)
    extraction_tables_image_detail: Literal["high", "auto"] = "high"
    extraction_tables_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    extraction_max_attempts: int = Field(default=3, ge=1, le=10)
    extraction_max_calls: int = Field(default=150, ge=1, le=10000)
    extraction_max_concurrent_per_run: int = Field(default=2, ge=1, le=32)
    extraction_max_concurrent_global: int = Field(default=4, ge=1, le=64)
    extraction_timeout_seconds: int = Field(default=60, ge=1, le=300)
    extraction_lease_seconds: int = Field(default=30, ge=3, le=600)
    extraction_backoff_seconds: int = Field(default=5, ge=0, le=300)
    extraction_redispatch_seconds: int = Field(default=30, ge=1, le=300)
    extraction_recovery_interval_seconds: int = Field(default=15, ge=1, le=300)
    extraction_fake_scenario: Literal[
        "success", "empty", "transient", "permanent", "invalid", "slow", "interrupted"
    ] = "success"
    extraction_pricing_basis: str | None = None
    extraction_input_usd_per_million: Decimal | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    extraction_output_usd_per_million: Decimal | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def extraction_pricing_is_complete(self) -> Self:
        rates = (self.extraction_input_usd_per_million, self.extraction_output_usd_per_million)
        if any(rate is not None for rate in rates) and (
            any(rate is None for rate in rates) or not self.extraction_pricing_basis
        ):
            raise ValueError("Extraction pricing needs both rates and a recorded pricing basis")
        return self

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator(
        "s3_public_endpoint_url",
        "openai_api_key",
        "extraction_pricing_basis",
        "extraction_input_usd_per_million",
        "extraction_output_usd_per_million",
        mode="before",
    )
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
