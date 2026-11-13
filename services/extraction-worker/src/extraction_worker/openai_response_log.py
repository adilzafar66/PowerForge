"""Opt-in local recording of parsed OpenAI structured responses."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def save_structured_response(directory: str, response, **metadata) -> None:
    if not directory:
        return
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        return

    temporary = None
    try:
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump(mode="json")
        timestamp = datetime.now(UTC)
        destination = Path(directory)
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = {
            "received_at": timestamp.isoformat(),
            "response_id": getattr(response, "id", None),
            "status": getattr(response, "status", None),
            **metadata,
            "output_parsed": parsed,
        }
        target = destination / f"{timestamp:%Y%m%dT%H%M%S.%fZ}-{uuid4().hex}.json"
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination, prefix=".response-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(target)
    except (OSError, ValueError, TypeError):
        logger.warning("Could not save local OpenAI structured response")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary OpenAI response file")
