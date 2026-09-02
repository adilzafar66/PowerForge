from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from powerforge_api.db import database_ready
from powerforge_api.redis_check import redis_ready
from powerforge_shared.config import get_settings

router = APIRouter(tags=["health"])

ServiceStatus = Literal["ok", "unavailable"]
ReadyStatus = Literal["ok", "degraded", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: ReadyStatus
    service: str
    version: str
    database: ServiceStatus
    redis: ServiceStatus


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/ready", response_model=ReadyResponse)
@router.get("/api/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse | JSONResponse:
    settings = get_settings()
    database: ServiceStatus = "ok" if database_ready() else "unavailable"
    redis: ServiceStatus = "ok" if redis_ready() else "unavailable"
    if database == "unavailable":
        overall: ReadyStatus = "unavailable"
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif redis == "unavailable":
        overall = "degraded"
        code = status.HTTP_200_OK
    else:
        overall = "ok"
        code = status.HTTP_200_OK
    payload = ReadyResponse(
        status=overall,
        service=settings.app_name,
        version=settings.app_version,
        database=database,
        redis=redis,
    )
    return JSONResponse(content=payload.model_dump(), status_code=code)
