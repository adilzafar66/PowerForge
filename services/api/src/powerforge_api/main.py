import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from powerforge_api.routers.health import router as health_router
from powerforge_api.routers.projects import router as projects_router
from powerforge_api.storage.factory import get_object_storage
from powerforge_shared.config import get_settings
from powerforge_shared.logging import configure_logging

logger = logging.getLogger(__name__)


def _ensure_storage_bucket() -> None:
    """Best-effort bucket check. Storage being down must not stop the API from booting."""
    try:
        storage = get_object_storage()
        storage.ensure_bucket()
    except Exception as exc:
        logger.warning(
            "object storage unavailable at startup; uploads will fail until it is reachable",
            extra={"error_class": type(exc).__name__},
        )
        return
    logger.info("object storage ready", extra={"bucket": get_settings().s3_bucket})


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    await asyncio.to_thread(_ensure_storage_bucket)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="PowerForge API",
        version=settings.app_version,
        description=(
            "Engineering data extraction platform API. "
            "Phase 1: health/readiness and project/revision management."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(projects_router)
    return application


app = create_app()
