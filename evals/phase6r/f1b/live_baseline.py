"""Operator-only Stage 1 baseline, using the production adapter and local publication replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import monotonic
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from occurrence_eval import EVALS, check_corpus, digest, read_gold, score
from openai import OpenAI
from pydantic import ValidationError
from stage1_preflight import ARMS, ExperimentOCR, Recipe, as_request, comparable, harness

from extraction_worker.openai_extraction import OpenAIExtractionProvider
from extraction_worker.spatial_evaluation import render
from extraction_worker.tesseract import TesseractProvider
from powerforge_ai.extraction import ProviderFailure, ResponseValidationFailure
from powerforge_extraction.extraction_profile import extraction_profile
from powerforge_extraction.identities import identity_hash
from powerforge_extraction.provider_body import dispatch_hash, encoded_body, responses_body
from powerforge_extraction.publication import build_publication
from powerforge_extraction.stage_contracts import parse_response
from powerforge_shared.config import Settings

MAX_CALLS = 62
PHASE_CAPS = {"baseline": 32, "development-candidate": 14, "holdout": 16}
CANDIDATE = "occurrence-evidence-v1"
CENTIMICRO_USD_RESERVATION = 53_326_680
CENTIMICRO_USD_CAP = 3_400_000_000
APPROVAL_TOKEN = "F1B-62-USD34"
ORIGIN = "https://api.openai.com/v1"
REPO = EVALS.parent


class Ledger:
    def __init__(self, work: Path):
        self.work = work
        self.path = work / "dispatches.sqlite3"
        with closing(self.connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS dispatches "
                "(slot TEXT PRIMARY KEY, work_unit TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, "
                "reserved INTEGER NOT NULL, admitted_at TEXT NOT NULL, result TEXT)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def existing(self, slot):
        with closing(self.connect()) as db:
            row = db.execute("SELECT result FROM dispatches WHERE slot=?", (slot,)).fetchone()
        if row is None:
            return None
        if row[0] is None:
            # A reserved send with no outcome stays charged and is never retried.
            return {"slot": slot, "state": "UNKNOWN_PROVIDER_OUTCOME", "budget_reserved": True}
        return json.loads(row[0])

    def reserve(self, slot, work_unit, body_hash, phase_cap):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            used, reserved = db.execute(
                "SELECT count(*), coalesce(sum(reserved),0) FROM dispatches"
            ).fetchone()
            phase = slot.partition("/")[0]
            phase_used = db.execute(
                "SELECT count(*) FROM dispatches WHERE slot LIKE ?", (phase + "/%",)
            ).fetchone()[0]
            if (
                used >= MAX_CALLS
                or phase_used >= phase_cap
                or reserved + CENTIMICRO_USD_RESERVATION > CENTIMICRO_USD_CAP
            ):
                raise ValueError("approved call or spend budget exhausted")
            db.execute(
                "INSERT INTO dispatches VALUES(?,?,?,?,?,NULL)",
                (
                    slot,
                    str(work_unit),
                    body_hash,
                    CENTIMICRO_USD_RESERVATION,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def settle(self, slot, result):
        with closing(self.connect()) as db, db:
            count = db.execute(
                "UPDATE dispatches SET result=? WHERE slot=? AND result IS NULL",
                (json.dumps(result, ensure_ascii=False), slot),
            ).rowcount
            if count != 1:
                raise ValueError("dispatch settlement must address a unique pending slot")

    def retain(self, unit, raw):
        path = self.work / f"{unit}.response"
        with path.open("xb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        return dict(
            sha256=hashlib.sha256(raw).hexdigest(),
            size=len(raw),
            expires_at=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
        )


def new_attempt(wire, request, pinned):
    work_unit = uuid4()
    return (
        wire,
        request.model_copy(update={"work_unit_id": work_unit}),
        replace(pinned, unit_id=work_unit),
    )


def send_one(ledger, api_key, settings, profile, slot, gold, bundle, phase_cap):
    existing = ledger.existing(slot)
    if existing is not None:
        return existing
    wire, request, pinned = new_attempt(*bundle)
    expected = dispatch_hash(request)
    body = responses_body(request, request.response_model)
    reserved = False
    started = monotonic()
    status = None

    def guard(http):
        nonlocal reserved
        if (
            reserved
            or http.method != "POST"
            or str(http.url) != ORIGIN + "/responses"
            or http.headers.get("X-Client-Request-Id") != str(request.work_unit_id)
            or identity_hash(json.loads(http.content)) != expected
            or request.stage != "EQUIPMENT_RECOGNITION"
            or body["model"] != "gpt-6-luna"
            or body["max_output_tokens"] != 16384
            or body.get("store") is not False
            or body.get("service_tier") != "default"
            or "tools" in body
            or request.timeout_seconds != 100
        ):
            raise ValueError("outgoing body differs from the approved pinned Stage 1 request")
        ledger.reserve(slot, request.work_unit_id, expected, phase_cap)
        reserved = True

    def response_header(response):
        nonlocal status
        status = response.status_code

    result = dict(
        slot=slot,
        work_unit=str(request.work_unit_id),
        request_sha256=expected,
        request_bytes=len(encoded_body(body)),
        expected_occurrences=len(gold.occurrences),
    )
    http = httpx.Client(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [guard], "response": [response_header]},
    )
    try:
        with OpenAI(
            api_key=api_key, base_url=ORIGIN, max_retries=0, timeout=100, http_client=http
        ) as client:
            response = OpenAIExtractionProvider(settings, profile, client).execute(request)
        provider_seconds = monotonic() - started
        result.update(
            provider_seconds=round(provider_seconds, 3),
            http_status=status,
            usage=response.usage.model_dump(mode="json"),
            audit=ledger.retain(request.work_unit_id, response.output_text),
        )
        if response.failure:
            raise response.failure
        admitted = parse_response(wire, response.output_text)
        # Run the same projection used by the worker. Evaluation artifacts are
        # isolated from the product database and do not claim a committed write.
        observations = build_publication(wire, admitted, pinned)
        from stage1_preflight import observations_from_output

        scored = observations_from_output(
            pinned, wire, response.output_text, dispatched_digest=expected, request=request
        )
        result.update(
            state="ADMITTED",
            admitted_count=len(admitted.equipment),
            projected_candidates=len(observations),
            projected_evidence_fragments=sum(len(item.evidence) for item in observations),
            score=score(gold, scored),
        )
    except ProviderFailure as exc:
        result.update(
            state="PROVIDER_FAILURE",
            error_code=str(exc.code),
            http_status=status,
            diagnostics=[item.model_dump(mode="json") for item in exc.diagnostics],
        )
    except ValidationError as exc:
        result.update(
            state="ADMISSION_FAILED",
            http_status=status,
            diagnostics=[
                dict(error_type=item["type"], path=item["loc"])
                for item in exc.errors(include_input=False)[:16]
            ],
        )
    except ResponseValidationFailure as exc:
        result.update(
            state="ADMISSION_FAILED",
            http_status=status,
            diagnostics=[exc.issue.model_dump(mode="json")],
        )
    except Exception as exc:
        result.update(state="LOCAL_FAILURE", http_status=status, error_type=type(exc).__name__)
    result["elapsed_seconds"] = round(monotonic() - started, 3)
    if not reserved:
        raise RuntimeError(
            f"no request admitted for {slot}: {result.get('error_code', result.get('error_type'))}"
        )
    ledger.settle(slot, result)
    print(f"{slot}: {result['state']} ({result['elapsed_seconds']} s)", flush=True)
    return result


def run(source_dir, work, ocr, preflight, pair_limit, rasters=None, workers=1, phase="baseline"):
    gold = read_gold()
    check_corpus(gold, source_dir)
    if work.is_symlink() or work.resolve().is_relative_to(REPO):
        raise ValueError("raw audit workspace must be a private directory outside the repository")
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.stat().st_mode & 0o077:
        raise ValueError("audit workspace permissions must be 0700")
    ledger = Ledger(work)
    api_key = os.getenv("OPENAI_API_KEY") or dotenv_values(REPO / ".env").get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("approved OpenAI key is unavailable")
    settings = Settings(_env_file=None, extraction_external_enabled=True, openai_api_key=api_key)
    profiles = {
        variant: extraction_profile(
            harness.settings_for(ocr).model_copy(
                update={"extraction_recognition_prompt_variant": variant}
            )
        )
        for variant in ("legacy", CANDIDATE)
    }
    layouts = {
        "baseline": [(arm, arm, "legacy") for arm in ARMS],
        "development-candidate": [(CANDIDATE, "positioned_only", CANDIDATE)],
        "holdout": [(variant, "positioned_only", variant) for variant in ("legacy", CANDIDATE)],
    }[phase]
    expected_input = {(r["source_sha256"], r["page"]): r for r in preflight}
    engines = {
        "native": ocr,
        "hybrid_300": ocr,
        "hybrid_300_line_removal": ExperimentOCR(ocr, Recipe(preprocess="remove_lines")),
    }
    groups = {
        "baseline": (
            ("development", gold.development),
            ("structural_control", gold.structural_control),
        ),
        "development-candidate": (("development", gold.development),),
        "holdout": (("synthetic_holdout", gold.synthetic_holdout),),
    }
    if phase != "baseline":
        with closing(ledger.connect()) as db:
            settled = db.execute(
                "SELECT count(*) FROM dispatches WHERE result IS NOT NULL "
                "AND slot LIKE 'baseline/%'"
            ).fetchone()[0]
        if settled != PHASE_CAPS["baseline"]:
            raise ValueError("baseline must settle before the controlled correction")
    jobs = []
    for split, docs in groups[phase]:
        for doc in docs:
            path = (source_dir if split == "development" else EVALS) / doc.pdf
            data = path.read_bytes()
            for page in doc.pages:
                if pair_limit is not None and len(jobs) >= pair_limit:
                    break
                image = render(path, data, page.pdf_page)
                if rasters is not None:
                    pinned_png = rasters / f"{doc.sha256}-{page.pdf_page}.png"
                    image = replace(image, analysis_png=pinned_png.read_bytes())
                bundles = {}
                controls = []
                for label, arm, variant in layouts:
                    bundle = as_request(
                        path,
                        data,
                        image,
                        page.pdf_page,
                        page.preparation,
                        engines[page.preparation],
                        arm,
                        recognition_variant=variant,
                    )
                    wire, request, pinned = bundle
                    pinned_expected = expected_input[(doc.sha256, page.pdf_page)]
                    control = pinned_expected["arms"][arm]
                    if (
                        pinned_expected["preparation"] != page.preparation
                        or control["image_sha256"] != wire.page.image_sha256
                        or control["reading_count"] != len(wire.page.readings)
                        or control["table_count"] != len(pinned.layout.tables)
                    ):
                        raise ValueError(f"live benchmark differs from preflight: {doc.pdf}")
                    controls.append(comparable(wire))
                    bundles[label] = bundle, profiles[variant]
                if any(control != controls[0] for control in controls[1:]):
                    raise ValueError("comparison changes more than the approved experimental axis")
                jobs.append((split, doc, page, bundles))
    halt = Event()

    def evaluate_page(index, job):
        split, doc, page, bundles = job
        local = []
        try:
            for repeat in range(2):
                labels = tuple(bundles)
                order = labels if (index + 1 + repeat) % 2 else labels[::-1]
                for arm in order:
                    if halt.is_set():
                        return local
                    page_slot = f"{phase}/{split}/{doc.sha256[:12]}/p{page.pdf_page}"
                    slot = f"{page_slot}/{repeat + 1}/{arm}"
                    previously_reserved = ledger.existing(slot) is not None
                    result = send_one(
                        ledger,
                        api_key,
                        settings,
                        bundles[arm][1],
                        slot,
                        page,
                        bundles[arm][0],
                        PHASE_CAPS[phase],
                    )
                    local.append(
                        result
                        | dict(
                            split=split, pdf=doc.pdf, page=page.pdf_page, arm=arm, repeat=repeat + 1
                        )
                    )
                    if not previously_reserved and (
                        result.get("state") in ("UNKNOWN_PROVIDER_OUTCOME", "LOCAL_FAILURE")
                        or result.get("http_status") not in (None, 200)
                        or result.get("error_code") in ("PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE")
                    ):
                        halt.set()
                        return local
        except Exception:
            halt.set()
            raise
        return local

    with ThreadPoolExecutor(max_workers=workers) as executor:
        calls = [executor.submit(evaluate_page, index, job) for index, job in enumerate(jobs)]
        return [result for call in calls for result in call.result()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("private_work", type=Path)
    parser.add_argument("--tesseract", required=True)
    parser.add_argument("--tessdata", required=True)
    parser.add_argument("--send-approval", choices=[APPROVAL_TOKEN], required=True)
    parser.add_argument("--pairs", type=int, choices=range(1, 9))
    parser.add_argument("--rasters", type=Path)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--phase", choices=tuple(PHASE_CAPS), default="baseline")
    parser.add_argument("--approved-correction-sha256")
    args = parser.parse_args()
    if args.phase != "baseline":
        guide = (
            REPO
            / "packages/extraction/src/powerforge_extraction/prompts"
            / "equipment_recognition_occurrence_evidence_v1.txt"
        )
        if args.approved_correction_sha256 != digest(guide.read_bytes()):
            parser.error("the correction phase requires the separately approved prompt digest")
    os.umask(0o077)
    preflight = json.loads(Path(__file__).with_name("preflight.json").read_text())
    results = run(
        args.source_dir,
        args.private_work,
        TesseractProvider(args.tesseract, args.tessdata),
        preflight,
        args.pairs,
        args.rasters,
        args.workers,
        args.phase,
    )
    report = args.private_work / (args.phase + ".json")
    report.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
