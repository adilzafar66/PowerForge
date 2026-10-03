"""Map SQLAlchemy IntegrityError to domain errors by PostgreSQL constraint name."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from powerforge_api.exceptions import ProjectError, UnexpectedIntegrityError

logger = logging.getLogger(__name__)


def constraint_name(exc: BaseException) -> str | None:
    """Return ``exc.orig.diag.constraint_name`` when present, else ``None``."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    name = getattr(diag, "constraint_name", None)
    if not name:
        return None
    return name


def _sqlstate(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    state = getattr(orig, "sqlstate", None)
    if state:
        return state
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    return getattr(diag, "sqlstate", None) or None


def translate_integrity_error(
    exc: IntegrityError,
    mapping: Mapping[str, ProjectError],
    *,
    operation: str,
) -> ProjectError:
    """Return the mapped domain error, or a generic unexpected error if unknown.

    Logs only the operation, constraint name, and SQLSTATE. The raw database
    message and statement parameters are omitted because they embed user data.
    """
    name = constraint_name(exc)
    if name is not None and name in mapping:
        return mapping[name]
    logger.error(
        "Unmapped integrity error during %s (constraint=%s, sqlstate=%s)",
        operation,
        name,
        _sqlstate(exc),
    )
    return UnexpectedIntegrityError()


@contextmanager
def integrity_guard(
    session: Session,
    mapping: Mapping[str, ProjectError],
    *,
    operation: str,
) -> Iterator[None]:
    """Rollback and translate ``IntegrityError``; other exceptions pass through."""
    try:
        yield
    except IntegrityError as exc:
        session.rollback()
        raise translate_integrity_error(exc, mapping, operation=operation) from exc
