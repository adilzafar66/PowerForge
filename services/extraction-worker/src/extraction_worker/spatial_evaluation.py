"""Offline paired spatial evaluation using the production parser, OCR and converters."""

import argparse
import json
import platform
import resource
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from PIL import __version__ as pillow_version

from extraction_worker.spatial_evaluation_gold import VERSION, load_cases, read_source
from extraction_worker.spatial_evaluation_legacy import prose_pair
from extraction_worker.spatial_evaluation_scoring import (
    aggregate,
    raw_readings,
    score_claims,
    score_layout,
)
from extraction_worker.tesseract import TesseractProvider
from powerforge_ai.ocr import OCRFailure
from powerforge_document_model.profile import DEFAULT_PROFILE
from powerforge_document_processing.layout_derive import derive_layout, layout_rules_identity
from powerforge_document_processing.rendering import RenderingFailed, open_rendered_pages
from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS
from powerforge_extraction.enriched_output import convert_attributes, convert_equipment
from powerforge_extraction.enriched_profiles import ENGINEERING_TEST, TABLES_TEST, enriched_profile
from powerforge_extraction.enriched_runtime import projection
from powerforge_extraction.enriched_sources import BoundSnapshot, load_bound
from powerforge_extraction.enriched_tables import interpret, reconstruct
from powerforge_extraction.enrichment_prepare import prepare_page, sha
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.identities import canonical_json, identity_hash
from powerforge_extraction.layout_profiles import layout_execution_identity
from powerforge_extraction.layout_sources import PreparedSnapshot
from powerforge_extraction.table_eval import evaluate as evaluate_tables
from powerforge_provenance.spatial_sources import OriginalDocument, PageArtifactRef, PageOwner
from powerforge_shared.config import Settings


def cpu_seconds(who):
    usage = resource.getrusage(who)
    return usage.ru_utime + usage.ru_stime


@contextmanager
def measure(stages, name):
    wall = perf_counter()
    own = cpu_seconds(resource.RUSAGE_SELF)
    children = cpu_seconds(resource.RUSAGE_CHILDREN)
    stats = stages.setdefault(name, {})
    try:
        yield stats
    finally:
        stats.update(
            {
                "wall_ms": round((perf_counter() - wall) * 1000, 2),
                "process_cpu_ms": round((cpu_seconds(resource.RUSAGE_SELF) - own) * 1000, 2),
                "child_cpu_ms": round((cpu_seconds(resource.RUSAGE_CHILDREN) - children) * 1000, 2),
            }
        )


class MeteredStorage(InMemoryObjectStorage):
    def __init__(self, destination):
        super().__init__()
        self.destination = destination
        self.artifacts = {}
        self.bytes_read = 0

    def retain(self, name, data):
        self.put(name, BytesIO(data), len(data), "application/octet-stream")
        self.artifacts[name] = {"sha256": sha(data), "size_bytes": len(data)}
        if self.destination:
            (self.destination / name).write_bytes(data)
        return name

    def get(self, key):
        stream = super().get(key)
        self.bytes_read += stream.getbuffer().nbytes
        return stream


def render(path, data, page_number):
    with TemporaryDirectory(prefix="powerforge-spatial-eval-") as directory:
        pinned = Path(directory) / path.name
        pinned.write_bytes(data)
        with open_rendered_pages(
            pinned, path.suffix, DEFAULT_PROFILE, DEFAULT_PROFILE.max_total_pixels, 50
        ) as document:
            for page in document:
                if page.page_number == page_number:
                    return page
    raise ValueError("Selected evaluation page is absent")


def prepare(case, file, data, page, storage, profile, provider_factory, before_ocr):
    owner = PageOwner(
        document_id=uuid4(),
        processing_run_id=uuid4(),
        document_page_id=uuid4(),
        page_number=case.page,
    )
    original = OriginalDocument(
        document_id=owner.document_id,
        sha256=case.sha256,
        size_bytes=case.size_bytes,
        format=file.suffix[1:].lower(),
    )
    base = PageArtifactRef(
        id=uuid4(),
        owner=owner,
        role="ANALYSIS_IMAGE",
        sha256=sha(page.analysis_png),
        size_bytes=len(page.analysis_png),
        width_px=page.width_px,
        height_px=page.height_px,
    )
    base_items = {base.id: page.analysis_png}
    artifacts = [base]
    if page.native_text:
        native = page.native_text.encode()
        ref = PageArtifactRef(
            id=uuid4(),
            owner=owner,
            role="NATIVE_TEXT",
            sha256=sha(native),
            size_bytes=len(native),
        )
        artifacts.append(ref)
        base_items[ref.id] = native
        storage.retain("analysis-native.txt", native)
    storage.retain("analysis.png", page.analysis_png)
    storage.retain("thumbnail.webp", page.thumbnail)
    output = prepare_page(
        owner,
        original,
        data,
        tuple(artifacts),
        base_items,
        uuid4(),
        uuid4(),
        profile.identity_hash,
        profile,
        case.force_ocr,
        provider_factory,
        before_ocr,
    )
    objects = []
    for ref, blob in output.blobs.values():
        key = storage.retain(str(ref.id), blob)
        objects.append((ref, key))
    storage.retain(
        "prepared.json", canonical_json(output.manifest.model_dump(mode="json")).encode()
    )
    return output, PreparedSnapshot(output.manifest, tuple(objects)), base


def derive(snapshot, output, base, storage):
    geometry = {
        r.ref: output.blobs[r.geometry_artifact.id][1] for r in snapshot.manifest.representations
    }
    text = {r.ref: output.blobs[r.text_artifact.id][1] for r in snapshot.manifest.representations}
    layout = derive_layout(snapshot.manifest, geometry, text, uuid4(), uuid4(), uuid4())
    payload = canonical_json(layout.model_dump(mode="json")).encode()
    key = storage.retain("layout.json", payload)
    return BoundSnapshot(snapshot, layout, key, len(payload), sha(payload), base, "analysis.png")


def with_stage(sources, stage):
    return replace(
        sources,
        stage=stage,
        unit_id=uuid4(),
        unit_key=f"{stage}:page:{sources.prepared.owner.page_number:06d}",
    )


def script(sources, profile, stats, storage, upstream=None):
    request = SimpleNamespace(
        text=projection(sources, profile),
        stage=sources.stage,
        schema_version=SCHEMAS[sources.stage],
        response_model=RESPONSES[sources.stage],
        upstream_context=canonical_json(upstream) if upstream is not None else None,
    )
    stats.update(
        source_projection_bytes=len(request.text.encode()),
        upstream_bytes=len((request.upstream_context or "").encode()),
    )
    # The deterministic provider sees observed source readings and admitted cells.
    response = FakeEnrichedProvider().execute(request).result
    storage.retain(sources.stage.lower() + "-observation.json", response.model_dump_json().encode())
    return response


def replay(sources, family, profile, stages, failures, storage):
    outputs = []
    stage = profile.stages[0]
    try:
        with measure(stages, stage) as stats:
            first = with_stage(sources, stage)
            observation = script(first, profile, stats, storage)
            if family == "prose":
                recognition = convert_equipment(observation, first)
                outputs.append(recognition)
                upstream = {
                    "equipment": [
                        {"local_ref": c.diagnostics["source_local_ref"]}
                        for c in recognition.candidates
                    ]
                }
            else:
                reconstructed, context = reconstruct(observation, first)
                outputs.append(reconstructed)
                if not context.tables:
                    return outputs
                upstream = {
                    "tables": [
                        {
                            "table_ref": t.observation.local_ref,
                            "observation": t.observation.model_dump(mode="json"),
                            "structure_basis": t.basis,
                        }
                        for t in context.tables
                    ]
                }
        stage = profile.stages[1]
        with measure(stages, stage) as stats:
            later = with_stage(first, stage)
            observation = script(later, profile, stats, storage, upstream)
            converted = (
                convert_attributes(observation, later, recognition)
                if family == "prose"
                else interpret(observation, later, context)
            )
            outputs.append(converted)
    except ValueError:
        failures.append({"stage": stage, "code": "INVALID_SCRIPTED_RESPONSE"})
    return outputs


def run_case(case, file, data, prep_profile, provider_factory, profiles, artifact_root):
    stages, failures = {}, []
    if artifact_root:
        artifact_root.mkdir()
    storage = MeteredStorage(artifact_root)
    storage.retain("original" + file.suffix, data)
    output = layout = sources = page = None
    invocations = 0

    def before_ocr():
        nonlocal invocations
        invocations += 1

    try:
        stage = "render"
        with measure(stages, stage):
            page = render(file, data, case.page)
        stage = "preparation"
        with measure(stages, stage):
            output, prepared, base = prepare(
                case, file, data, page, storage, prep_profile, provider_factory, before_ocr
            )
        stage = "layout"
        with measure(stages, stage):
            snapshot = derive(prepared, output, base, storage)
            layout = snapshot.layout
        stage = "source_replay"
        with measure(stages, stage):
            sample = SimpleNamespace(run_id=uuid4(), id=uuid4(), unit_key="eval", stage="eval")
            sources = load_bound(snapshot, storage, sample, profiles["tables"])
    except (OCRFailure, RenderingFailed, OSError, ValueError) as exc:
        failures.append({"stage": stage, "code": str(getattr(exc, "code", type(exc).__name__))})

    # Score preparation even when the independent downstream layout/source replay failed.
    bodies = sources.bodies if sources else {}
    if not bodies and output:
        from powerforge_provenance.spatial_sources import load_positioned_text

        for ref in output.manifest.representations:
            body, _ = load_positioned_text(
                output.manifest,
                ref.ref,
                output.blobs[ref.geometry_artifact.id][1],
                output.blobs[ref.text_artifact.id][1],
            )
            bodies[ref.ref] = body
    raw, supports = raw_readings(case, bodies)
    structural, tables = score_layout(case, layout, supports)
    result = {
        "id": case.id,
        "page": case.page,
        "source": case.source,
        "source_sha256": case.sha256,
        "source_provenance": "SYNTHETIC_AUTHORED",
        "force_ocr": case.force_ocr,
        "ocr_decision": output.manifest.ocr_decision if output else None,
        "ocr_reason": output.manifest.ocr_reason if output else None,
        "ocr_usage": output.usage if output else None,
        "ocr_invocations_started": invocations,
        "source_artifacts": storage.artifacts,
        "page_rotation": page.rotation_degrees if page else None,
        "processing_bytes": {
            "original": len(data),
            "stored": sum(a["size_bytes"] for a in storage.artifacts.values()),
            "source_replay_read": storage.bytes_read,
        },
        "stages": stages,
        "preprocessing": {**raw, **structural},
        "table_details": tables,
        "unresolved_reasons": [item.reason for item in layout.unresolved] if layout else [],
        "mock_conversion": {},
        "failures": failures,
    }
    for family, profile in profiles.items():
        outputs = replay(sources, family, profile, stages, failures, storage) if sources else []
        metrics, details = score_claims(case, outputs, sources, supports, family)
        result["mock_conversion"][family] = {"metrics": metrics, "claims": details}
        if outputs:
            storage.retain(
                f"{family}-converted.json",
                canonical_json([o.model_dump(mode="json") for o in outputs]).encode(),
            )
    result["processing_bytes"]["replay_artifact_bytes"] = (
        sum(a["size_bytes"] for a in storage.artifacts.values())
        - result["processing_bytes"]["stored"]
    )
    return result, page


def table_pair(root, case, result):
    base = root / "tables/v1"
    # Replay the original gold and recordings. The paired fixture's digest is also
    # checked independently by both corpus loaders.
    frozen = evaluate_tables(
        base / "corpus.json", base / "scripted.json", ["pdf_native_unresolved", "pdf_hybrid"]
    )
    manifest = json.loads((base / "corpus.json").read_text())
    for row in manifest["cases"]:
        if row["id"] in {"pdf_native_unresolved", "pdf_hybrid"} and (
            row["source_document"]["sha256"] != case.sha256 or case.page != 1
        ):
            raise ValueError("6D pair no longer uses the exact same source page")
    return {
        "source_sha256": case.sha256,
        "page": case.page,
        "legacy_replays": {row["case_id"]: row["counts"] for row in frozen["cases"]},
        "enhanced": result["mock_conversion"]["tables"]["metrics"],
        "enhanced_supported_partition": result["preprocessing"]["supported_partition_recall"],
        "policy": "Common printed claim meanings; legacy v1 and spatial v1 evidence scores differ.",
    }


def strata(results):
    grouped = defaultdict(list)
    for row in results:
        for table in row["table_details"]:
            for factor in table["factors"]:
                grouped[factor].append(table)
            grouped["reading_basis_" + table["gold_reading_basis"]].append(table)
            outside = set(table["factors"]) - {"regular_borderless", "ruled"}
            if "ruled" not in table["factors"]:
                grouped[
                    "outside_borderless_assumptions" if outside else "within_borderless_assumptions"
                ].append(table)
    return {
        name: {
            "gold": len(tables),
            "matched_region": sum(t["geometry_matched"] for t in tables),
            "supported_partition": sum(t["partition_correct"] for t in tables),
            "missed_or_incorrect_partition": sum(not t["partition_correct"] for t in tables),
            "false_supported_partition_matched_here": sum(t["false_partition"] for t in tables),
            "unresolved_retained": sum(t["unresolved_retained"] for t in tables),
        }
        for name, tables in sorted(grouped.items())
    }


class NumericErrorControl:
    """Inject one plausible misreading after actual OCR. Never counted as engine quality."""

    def __init__(self, provider):
        self.provider = provider
        self.identity, self.settings = provider.identity, provider.settings
        self.replacements = 0

    def recognize(self, request):
        actual = self.provider.recognize(request)
        words = list(actual.words)
        for i, word in enumerate(words):
            if word.text == "690":
                words[i] = word.model_copy(update={"text": "600"})
                self.replacements += 1
                break
        return actual.model_copy(update={"words": tuple(words)})


def evaluate(corpus, root, *, selected=None, artifacts=None, binary=None, data_directory=None):
    cases, corpus_sha = load_cases(corpus, root, selected)
    options = {}
    if binary is not None:
        options["binary"] = binary
    if data_directory is not None:
        options["data_directory"] = data_directory
    provider = TesseractProvider(**options)
    config = {
        "identity": provider.identity.model_dump(mode="json"),
        "settings": provider.settings.model_dump(mode="json"),
    }
    settings = Settings(
        _env_file=None, enrichment_enabled=True, enrichment_ocr_configuration=json.dumps(config)
    )
    prep = preparation_profile(settings)
    profiles = {
        "prose": enriched_profile(ENGINEERING_TEST, settings),
        "tables": enriched_profile(TABLES_TEST, settings),
    }
    results, comparisons, controls = [], {}, {}
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=False)
    for case, file in cases:
        data = read_source(case, file)
        result, page = run_case(
            case,
            file,
            data,
            prep,
            lambda: provider,
            profiles,
            artifacts / case.id if artifacts else None,
        )
        results.append(result)
        if case.baseline == "table-pdf":
            comparisons[case.id] = table_pair(root, case, result)
        elif case.baseline:
            comparisons[case.id] = prose_pair(case, page, result)
        if case.id == "scanned-schedule":
            control = NumericErrorControl(provider)
            changed, _ = run_case(
                case,
                file,
                data,
                prep,
                lambda control=control: control,
                profiles,
                artifacts / "injected-numeric-error" if artifacts else None,
            )
            controls["injected_numeric_error"] = {
                "provenance": "ACTUAL_LOCAL_OCR_WITH_INJECTED_NUMERIC_ERROR",
                "replacements": control.replacements,
                "result": changed,
            }
    local = files("extraction_worker")
    metrics = aggregate(row["preprocessing"] for row in results)
    metrics.record(
        "source_pages_completed",
        sum(
            "source_replay" in r["stages"]
            and not any(
                f["stage"] in {"render", "preparation", "layout", "source_replay"}
                for f in r["failures"]
            )
            for r in results
        ),
        len(results),
    )
    metrics.record(
        "pages_without_stage_errors", sum(not r["failures"] for r in results), len(results)
    )
    groups = strata(results)
    outside = groups.get("outside_borderless_assumptions", {}).get("gold", 0)
    within = groups.get("within_borderless_assumptions", {}).get("gold", 0)
    metrics.record("outside_borderless_assumptions", outside, outside + within)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    child_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    multiplier = 1 if platform.system() == "Darwin" else 1024
    return {
        "version": VERSION,
        "corpus_sha256": corpus_sha,
        "source_provenance": "SYNTHETIC_AUTHORED",
        "ocr_provenance": "ACTUAL_LOCAL_TESSERACT",
        "model_provenance": "DETERMINISTIC_SOURCE_MOCK",
        "live_openai_quality_measured": False,
        "real_document_coverage_measured": False,
        "provider_tokens": None,
        "provider_cost_usd": None,
        "environment": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pillow": pillow_version,
            "process_peak_rss_bytes": peak * multiplier,
            "child_peak_rss_bytes": child_peak * multiplier,
        },
        "resources": {
            "scorer_sha256": identity_hash(
                {
                    name: sha(local.joinpath(name).read_bytes())
                    for name in (
                        "spatial_evaluation.py",
                        "spatial_evaluation_gold.py",
                        "spatial_evaluation_legacy.py",
                        "spatial_evaluation_scoring.py",
                    )
                }
            ),
            "ocr": config,
            "native": prep.native,
            "preparation_profile": prep.identity_hash,
            "layout_algorithm": layout_rules_identity(),
            "layout_execution": layout_execution_identity(),
            "processing_profile": DEFAULT_PROFILE.profile_hash,
            "mock_profiles": {key: p.identity_hash for key, p in profiles.items()},
        },
        "bounds": {
            "processing": DEFAULT_PROFILE.material_fields(),
            "model_source_projection_bytes": 131072,
            "model_total_input_bytes": {
                key: p.max_total_input_bytes for key, p in profiles.items()
            },
        },
        "preprocessing": metrics,
        "table_strata": groups,
        "mock_conversion": {
            family: aggregate(r["mock_conversion"][family]["metrics"] for r in results)
            for family in profiles
        },
        "legacy_comparisons": comparisons,
        "controls": controls,
        "cases": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline spatial extraction evaluation v1")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument(
        "--source-root", type=Path, help="Defaults to the enclosing evals directory"
    )
    parser.add_argument("--case", dest="selected", action="append")
    parser.add_argument(
        "--artifacts", type=Path, help="New directory for exact source and derived bytes"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tesseract")
    parser.add_argument("--tessdata")
    args = parser.parse_args(argv)
    try:
        report = evaluate(
            args.corpus,
            args.source_root or args.corpus.resolve().parents[2],
            selected=args.selected,
            artifacts=args.artifacts,
            binary=args.tesseract,
            data_directory=args.tessdata,
        )
    except (OSError, OCRFailure, ValueError) as exc:
        parser.exit(2, f"Spatial evaluation setup failed ({type(exc).__name__})\n")
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
