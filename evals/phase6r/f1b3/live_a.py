"""Dispatch only the explicitly approved Investigation A manifest."""

import argparse
import json
import os
import signal
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from investigation_a import HERE, TIMEOUT_SECONDS, Reply, build_body, digest, preflight
from live_baseline import ORIGIN, REPO, Ledger
from pydantic import ValidationError

from extraction_worker.spatial_evaluation import render
from powerforge_extraction.provider_body import encoded_body

RESERVATION = 53_326_680  # 1e-8 USD
CAP = 660_000_000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
APPROVAL = "F1B3-A-12-USD6.60"


def slots(manifest):
    for repeat, order in enumerate(manifest["arm_orders"], 1):
        for page in manifest["pages"]:
            for arm in order:
                name = Path(page["pdf"]).stem
                yield f"{name}/{repeat}/{arm}", page, arm


class ApprovedLedger(Ledger):
    def __init__(self, work, manifest):
        super().__init__(work)
        self.allowed = {
            slot: page["requests"][arm]["body_sha256"] for slot, page, arm in slots(manifest)
        }

    def reserve_approved(self, slot, unit, body_sha):
        if self.allowed.get(slot) != body_sha:
            raise ValueError("Unapproved slot or request")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            count, reserved = db.execute(
                "SELECT count(*), coalesce(sum(reserved),0) FROM dispatches"
            ).fetchone()
            if count >= 12 or reserved + RESERVATION > CAP:
                raise ValueError("Investigation A budget exhausted")
            db.execute(
                "INSERT INTO dispatches VALUES(?,?,?,?,?,NULL)",
                (slot, str(unit), body_sha, RESERVATION, datetime.now(UTC).isoformat()),
            )


def estimate(usage):
    if not usage:
        return None
    inp = usage["input_tokens"]
    out = usage["output_tokens"]
    details = usage.get("input_tokens_details") or {}
    reads = details.get("cached_tokens", 0)
    writes = details.get("cache_write_tokens", 0)
    by_lifetime = details.get("cache_write_tokens_details") or {}
    short_writes = by_lifetime.get("ttl_30m_tokens", 0)
    long_writes = by_lifetime.get("ttl_12h_tokens", 0)
    if short_writes + long_writes != writes or reads + writes > inp:
        return None
    rates = ("0.20", "0.02", "0.75") if inp > 272_000 else ("0.10", "0.01", "0.50")
    base, cached, output = map(Decimal, rates)
    ordinary = inp - reads - writes
    total = (
        ordinary * base
        + reads * cached
        + short_writes * base * Decimal("1.25")
        + long_writes * base * Decimal("2.5")
        + out * output
    )
    return str(total / 1_000_000)


def review_envelope(body, arm, ledger, unit):
    texts = []
    refused = False
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif part.get("type") == "refusal":
                refused = True
    status = body.get("status")
    result = {
        "provider_response_id": body.get("id"),
        "model": body.get("model"),
        "service_tier": body.get("service_tier"),
        "provider_status": status,
        "usage": body.get("usage"),
        "usage_based_usd": estimate(body.get("usage")),
    }
    if len(texts) == 1:
        result["audit"] = ledger.retain(unit, texts[0].encode("utf-8"))
    elif len(texts) > 1:
        result["audit_parts"] = [
            ledger.retain(f"{unit}-{index}", value.encode("utf-8"))
            for index, value in enumerate(texts)
        ]
    if refused:
        return result | {"state": "REFUSED"}
    if status != "completed":
        reason = (body.get("incomplete_details") or {}).get("reason")
        return result | {
            "state": "INCOMPLETE" if status == "incomplete" else "PROVIDER_FAILURE",
            "incomplete_reason": reason
            if reason in {"max_output_tokens", "content_filter"}
            else None,
        }
    if len(texts) != 1 or not texts[0].strip():
        return result | {"state": "ADMISSION_FAILED", "diagnostic": "EXPECTED_ONE_OUTPUT_TEXT"}
    if arm != "A1":
        try:
            reply = Reply.model_validate_json(texts[0])
        except ValidationError as exc:
            fields = {"equipment", "identification", "type", "tag"}
            return result | {
                "state": "ADMISSION_FAILED",
                "validation_errors": [
                    {
                        "type": error["type"],
                        "path": [
                            part if isinstance(part, int) or part in fields else "[unknown]"
                            for part in error["loc"]
                        ],
                    }
                    for error in exc.errors(include_input=False)[:16]
                ],
            }
        result["structured_rows"] = len(reply.equipment)
    return result | {"state": "ADMITTED"}


def deadline(_signal, _frame):
    raise TimeoutError("Provider wall clock deadline")


def send(client, ledger, slot, arm, body, body_sha):
    prior = ledger.existing(slot)
    if prior is not None:
        return prior
    if digest(body) != body_sha:
        raise ValueError("Request bytes differ from reviewed manifest")
    unit = uuid4()
    ledger.reserve_approved(slot, unit, body_sha)
    result = {"slot": slot, "work_unit": str(unit), "request_sha256": body_sha}
    started = monotonic()
    previous = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_SECONDS)
    try:
        with client.stream(
            "POST",
            ORIGIN + "/responses",
            content=body,
            headers={"X-Client-Request-Id": str(unit)},
        ) as response:
            result["http_status"] = response.status_code
            result["provider_request_id"] = response.headers.get("x-request-id")
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=16384):
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ValueError("Provider response exceeds bound")
                content.extend(chunk)
        signal.setitimer(signal.ITIMER_REAL, 0)
        result["provider_seconds"] = round(monotonic() - started, 3)
        if response.is_success:
            result.update(review_envelope(json.loads(content), arm, ledger, unit))
        else:
            result["state"] = "HTTP_FAILURE"
            error = json.loads(content).get("error", {})
            for field in ("type", "code"):
                value = error.get(field)
                if isinstance(value, str) and value.isascii() and value.replace("_", "").isalnum():
                    result["error_" + field] = value[:80]
    except (TimeoutError, httpx.TransportError) as exc:
        result.update(state="UNKNOWN_PROVIDER_OUTCOME", error_type=type(exc).__name__)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        result.update(state="INVALID_ENVELOPE", error_type=type(exc).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    result["elapsed_seconds"] = round(monotonic() - started, 3)
    ledger.settle(slot, result)
    print(f"{slot} {result['state']} {result['elapsed_seconds']}s", flush=True)
    return result


def run(source_dir, work, stop_after):
    manifest = json.loads((HERE / "a-preflight.json").read_bytes())
    current = json.loads(json.dumps(preflight(source_dir)))
    if current != manifest:
        raise ValueError("Approval manifest drift")
    if work.is_symlink() or work.resolve().is_relative_to(REPO):
        raise ValueError("Private audit directory required")
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.stat().st_mode & 0o077:
        raise ValueError("Audit directory permissions must be 0700")
    ledger = ApprovedLedger(work, manifest)
    images = {}
    for page in manifest["pages"]:
        path = source_dir / page["pdf"]
        data = path.read_bytes()
        if digest(data) != page["pdf_sha256"]:
            raise ValueError("Source identity changed")
        png = render(path, data, page["pdf_page"]).analysis_png
        if digest(png) != page["analysis_png_sha256"]:
            raise ValueError("Source image identity changed")
        images[page["pdf"]] = png
    api_key = os.getenv("OPENAI_API_KEY") or dotenv_values(REPO / ".env").get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API credential unavailable")
    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        timeout=TIMEOUT_SECONDS,
        transport=httpx.HTTPTransport(retries=0, trust_env=False),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    ) as client:
        for slot, page, arm in list(slots(manifest))[:stop_after]:
            body = encoded_body(build_body(arm, images[page["pdf"]]))
            result = send(client, ledger, slot, arm, body, page["requests"][arm]["body_sha256"])
            if result.get("http_status") in {400, 401, 403, 404, 429}:
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--approval", required=True, choices=[APPROVAL])
    parser.add_argument("--stop-after", choices=[3, 6, 12], type=int, default=6)
    opts = parser.parse_args()
    run(opts.source_dir, opts.work, opts.stop_after)
