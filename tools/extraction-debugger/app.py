"""Opt-in, same-origin Extraction Debugger for a single local operator."""

import logging
import os
import secrets
import time
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from queries import AttemptDetail, AttemptPage, Validation, attempt_detail, list_attempts
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from powerforge_document_processing.storage.base import StorageError
from powerforge_document_processing.storage.s3 import S3ObjectStorage
from powerforge_extraction.audit_reader import AuditReadError, read_audit
from powerforge_shared.config import get_settings

HOST = "127.0.0.1:3100"
ORIGIN = f"http://{HOST}"
COOKIE = "powerforge_debugger"
DIST = Path(__file__).parent / "dist"


class Login(BaseModel):
    secret: str = Field(max_length=1024)


def create_app(secret, engine, storage, *, dist=DIST):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    session_token = None
    expires = 0.0

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse({"detail": "invalid_request"}, 422)

    @app.middleware("http")
    async def enforce_local_access(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.client is None
            or request.client.host != "127.0.0.1"
            or request.headers.get("host") != HOST
            or origin not in (None, ORIGIN)
        ):
            response = JSONResponse({"detail": "local_access_required"}, 403)
        elif request.method != "GET" and (
            origin != ORIGIN or request.headers.get("x-debugger-request") != "1"
        ):
            response = JSONResponse({"detail": "origin_check_failed"}, 403)
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != "/api/login"
            and (
                session_token is None
                or time.monotonic() >= expires
                or not secrets.compare_digest(
                    request.cookies.get(COOKIE, "").encode(), session_token.encode()
                )
            )
        ):
            response = JSONResponse({"detail": "authentication_required"}, 401)
        else:
            try:
                response = await call_next(request)
            except Exception:
                logging.getLogger("extraction-debugger").warning("Debugger request failed")
                response = JSONResponse({"detail": "service_unavailable"}, 503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.post("/api/login", status_code=204)
    def login(body: Login):
        nonlocal session_token, expires
        if not secrets.compare_digest(body.secret.encode(), secret.encode()):
            raise HTTPException(401, "authentication_failed")
        session_token = secrets.token_urlsafe(32)
        expires = time.monotonic() + 3600
        response = Response(status_code=204)
        response.set_cookie(COOKIE, session_token, httponly=True, samesite="strict", max_age=3600)
        return response

    @app.post("/api/logout", status_code=204)
    def logout():
        nonlocal session_token
        session_token = None
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, httponly=True, samesite="strict")
        return response

    @app.get("/api/attempts", response_model=AttemptPage)
    def attempts(
        identity: UUID | None = None,
        validation: Validation | None = None,
        status: Literal["COMPLETED", "FAILED", "CANCELLED"] | None = None,
        retention: bool | None = None,
        cursor: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return list_attempts(
            engine,
            identity=identity,
            validation=validation,
            status=status,
            retention=retention,
            cursor=cursor,
            limit=limit,
        )

    @app.get("/api/attempts/{attempt_id}", response_model=AttemptDetail)
    def detail(attempt_id: UUID):
        result = attempt_detail(engine, attempt_id)
        if result is None:
            raise HTTPException(404, "attempt_not_found")
        return result

    @app.post("/api/attempts/{attempt_id}/original")
    def original(attempt_id: UUID):
        return Response(verified(attempt_id), media_type="text/plain; charset=utf-8")

    @app.post("/api/attempts/{attempt_id}/export")
    def export(attempt_id: UUID):
        return Response(
            verified(attempt_id),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="stage2-{attempt_id}.json"'},
        )

    def verified(attempt_id):
        try:
            return read_audit(engine, storage, attempt_id)
        except AuditReadError as error:
            code = str(error)
            raise HTTPException(
                {
                    "expired": 410,
                    "object_missing": 404,
                    "not_captured": 404,
                    "integrity_failed": 409,
                }[code],
                code,
            ) from None
        except (SQLAlchemyError, StorageError):
            raise HTTPException(503, "audit_service_unavailable") from None

    if dist.joinpath("assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"))

    @app.get("/", include_in_schema=False)
    def index():
        if not dist.joinpath("index.html").is_file():
            raise HTTPException(503, "frontend_build_required")
        return FileResponse(dist / "index.html")

    return app


def main():
    if os.environ.get("EXTRACTION_DEBUGGER_ENABLED") != "1":
        raise SystemExit("Set EXTRACTION_DEBUGGER_ENABLED=1 to start the local debugger.")
    names = (
        "EXTRACTION_DEBUGGER_SECRET",
        "EXTRACTION_RESPONSE_AUDIT_DATABASE_URL",
        "EXTRACTION_RESPONSE_AUDIT_ENDPOINT_URL",
        "EXTRACTION_RESPONSE_AUDIT_BUCKET",
        "EXTRACTION_RESPONSE_AUDIT_READ_ACCESS_KEY",
        "EXTRACTION_RESPONSE_AUDIT_READ_SECRET_KEY",
    )
    values = [os.environ.get(name, "") for name in names]
    if not all(values) or len(values[0]) < 24:
        raise SystemExit(
            "Set all debugger settings and use a startup secret of at least 24 characters."
        )
    secret, database, endpoint, bucket, access, storage_secret = values
    try:
        url = make_url(database)
        if (
            url.drivername != "postgresql+psycopg"
            or not url.username
            or not url.password
            or url.username in {"postgres", "powerforge", os.environ.get("POSTGRES_USER")}
            or access
            in {
                "powerforge",
                "minioadmin",
                os.environ.get("MINIO_ROOT_USER"),
                os.environ.get("EXTRACTION_RESPONSE_AUDIT_WRITE_ACCESS_KEY"),
            }
        ):
            raise ValueError
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 4})
        storage = S3ObjectStorage(
            endpoint_url=endpoint,
            public_endpoint_url=None,
            access_key=access,
            secret_key=storage_secret,
            bucket=bucket,
            region=get_settings().s3_region,
        )
    except Exception:
        raise SystemExit("Invalid operator database or audit-storage configuration.") from None
    uvicorn.run(
        create_app(secret, engine, storage),
        host="127.0.0.1",
        port=3100,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
