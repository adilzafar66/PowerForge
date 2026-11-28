import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from live_a import ApprovedLedger, digest, estimate, review_envelope, send, slots

MANIFEST = json.loads(Path(__file__).with_name("a-preflight.json").read_text())


def test_ledger_uses_reviewed_slots_pins_and_budget(tmp_path):
    ledger = ApprovedLedger(tmp_path, MANIFEST)
    approved_slots = list(slots(MANIFEST))
    assert len(approved_slots) == 12
    for slot, page, arm in approved_slots:
        assert ledger.existing(slot) is None
        body_sha = page["requests"][arm]["body_sha256"]
        with pytest.raises(ValueError, match="Unapproved"):
            ledger.reserve_approved(slot, uuid4(), "different body")
        ledger.reserve_approved(slot, uuid4(), body_sha)
        assert ledger.existing(slot)["state"] == "UNKNOWN_PROVIDER_OUTCOME"
        with pytest.raises((sqlite3.IntegrityError, ValueError)):
            ledger.reserve_approved(slot, uuid4(), body_sha)


def envelope(text, *, status="completed"):
    return {
        "status": status,
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
    }


def test_validation_rejects_but_retains_exact_bytes_without_leaking_field_name(tmp_path):
    ledger = ApprovedLedger(tmp_path, MANIFEST)
    unit = uuid4()
    raw = '{"equipment":[],"private source text":true}\n'
    result = review_envelope(envelope(raw), "A2", ledger, unit)
    assert result["state"] == "ADMISSION_FAILED"
    assert result["validation_errors"] == [{"type": "extra_forbidden", "path": ["[unknown]"]}]
    assert (tmp_path / f"{unit}.response").read_bytes() == raw.encode()
    assert result["audit"]["sha256"] == digest(raw.encode())


def test_unknown_provider_outcome_cannot_retry(tmp_path):
    body = b'{"test":"body"}'
    slot = "synthetic/1/A1"
    ledger = ApprovedLedger(
        tmp_path,
        {
            "arm_orders": [["A1"]],
            "pages": [{"pdf": "synthetic.pdf", "requests": {"A1": {"body_sha256": digest(body)}}}],
        },
    )
    attempts = []

    def disconnect(request):
        attempts.append(request)
        raise httpx.ReadTimeout("provider outcome unavailable")

    with httpx.Client(transport=httpx.MockTransport(disconnect)) as client:
        first = send(client, ledger, slot, "A1", body, digest(body))
        second = send(client, ledger, slot, "A1", body, digest(body))
    assert first == second
    assert first["state"] == "UNKNOWN_PROVIDER_OUTCOME"
    assert len(attempts) == 1


def test_incomplete_response_is_audited_but_never_admitted(tmp_path):
    ledger = ApprovedLedger(tmp_path, MANIFEST)
    unit = uuid4()
    body = envelope('{"equipment":[]}', status="incomplete") | {
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    result = review_envelope(body, "A2", ledger, unit)
    assert result["state"] == "INCOMPLETE"
    assert result["incomplete_reason"] == "max_output_tokens"
    assert result["audit"]["sha256"] == digest(b'{"equipment":[]}')


def test_usage_pricing_charges_each_input_token_once():
    usage = {
        "input_tokens": 12000,
        "output_tokens": 1000,
        "input_tokens_details": {
            "cached_tokens": 4000,
            "cache_write_tokens": 7000,
            "cache_write_tokens_details": {"ttl_30m_tokens": 3000, "ttl_12h_tokens": 4000},
        },
    }
    assert Decimal(estimate(usage)) == Decimal("0.002015")
    usage["input_tokens_details"]["cache_write_tokens"] = 8000
    assert estimate(usage) is None
