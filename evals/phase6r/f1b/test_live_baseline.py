import hashlib
import sqlite3
from uuid import uuid4

import pytest
from live_baseline import Ledger


def test_reserved_unknown_slot_remains_charged_and_cannot_be_resent(tmp_path):
    ledger = Ledger(tmp_path)
    slot = "baseline/development/test/p1/1/positioned_only"
    work_unit = uuid4()
    ledger.reserve(slot, work_unit, "a" * 64, phase_cap=3)
    assert ledger.existing(slot)["state"] == "UNKNOWN_PROVIDER_OUTCOME"
    with pytest.raises(sqlite3.IntegrityError):
        ledger.reserve(slot, uuid4(), "b" * 64, phase_cap=3)
    ledger.settle(slot, {"state": "ADMITTED"})
    assert ledger.existing(slot) == {"state": "ADMITTED"}


def test_phase_cap_and_response_retention(tmp_path):
    ledger = Ledger(tmp_path)
    work_unit = uuid4()
    ledger.reserve("baseline/a", work_unit, "a" * 64, phase_cap=1)
    with pytest.raises(ValueError, match="budget exhausted"):
        ledger.reserve("baseline/b", uuid4(), "a" * 64, phase_cap=1)
    raw = b'{"equipment":[]}'
    tracked = ledger.retain(work_unit, raw)
    assert tracked["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / f"{work_unit}.response").read_bytes() == raw
    with pytest.raises(FileExistsError):
        ledger.retain(work_unit, b"other")
