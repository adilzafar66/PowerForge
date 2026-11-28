"""Build exact Investigation B bodies locally without provider transport."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from investigation_a import HERE, build_body, checked_gold, digest
from stage1_preflight import ExperimentOCR, Recipe, as_request

from extraction_worker.spatial_evaluation import render
from extraction_worker.tesseract import TesseractProvider
from powerforge_extraction.provider_body import encoded_body
from powerforge_extraction.stage_execution import provider_input
from powerforge_provenance.spatial_base import canonical_json

ARMS = ("B1", "B2", "B3")


def positioned_readings(page):
    """Preserve each preferred transcription, separate alternatives and position."""
    geometry = {item["ref"]: item for item in page["layout"]["readings"]}
    lines = ["Positioned readings. Coordinates are normalized page x, y, width, height."]
    for reading in page["readings"]:
        ref = reading["reading_ref"]
        location = geometry[ref]
        region = location["region"]
        coords = (
            ",".join(str(region[key]) for key in ("x", "y", "width", "height"))
            if region is not None
            else "unpositioned"
        )
        line = f"{ref} [{coords}] {json.dumps(reading['text'], ensure_ascii=False)}"
        if reading["alternate_texts"]:
            line += f" | alternatives {json.dumps(reading['alternate_texts'], ensure_ascii=False)}"
        if location["issues"]:
            line += " | " + ", ".join(location["issues"])
        lines.append(line)
    return "\n".join(lines)


def build_requests(png, page):
    control = build_body("A3", png)
    requests = {"B1": encoded_body(control)}
    for arm, projection in (
        ("B2", positioned_readings(page)),
        ("B3", canonical_json({"page": page})),
    ):
        content = [{"type": "input_text", "text": projection}, *control["input"][0]["content"]]
        requests[arm] = encoded_body(control | {"input": [{"role": "user", "content": content}]})
    return requests


def prepare(source_dir, rasters, private, engine, *, transformers=False):
    original, _, gold_sha = checked_gold(source_dir)
    manifest_a = json.loads((HERE / "a-preflight.json").read_bytes())
    rows = []
    line_engine = ExperimentOCR(engine, Recipe(preprocess="remove_lines"))
    sources = manifest_a["pages"]
    if transformers:
        previous = json.loads((HERE.parent / "f1b" / "preflight.json").read_bytes())
        sources = [
            {
                "pdf": row["pdf"],
                "pdf_page": row["page"],
                "pdf_sha256": row["source_sha256"],
                "analysis_png_sha256": row["arms"]["positioned_only"]["image_sha256"],
            }
            for row in previous
            if row["pdf"] in {"delta-transformer-drawing.pdf", "rex-transformer-drawing.pdf"}
        ]
        if len(sources) != 2:
            raise ValueError("Expected the two pinned transformer pages")
    for source in sources:
        path = source_dir / source["pdf"]
        doc = next(item for item in original.development if item.pdf == path.name)
        number = source["pdf_page"]
        data = path.read_bytes()
        png = (rasters / f"{doc.sha256}-{number}.png").read_bytes()
        if (digest(data), digest(png)) != (source["pdf_sha256"], source["analysis_png_sha256"]):
            raise ValueError("PDF or image differs from the pinned source")
        rendered = replace(render(path, data, number), analysis_png=png)
        selection = next(item.preparation for item in doc.pages if item.pdf_page == number)
        provider = line_engine if selection == "hybrid_300_line_removal" else engine
        wire, _, pinned = as_request(
            path, data, rendered, number, selection, provider, "positioned_only"
        )
        page = provider_input(wire)["page"]
        if pinned.layout.tables:
            raise ValueError("Expected positioned-only preparation")
        bodies = build_requests(png, page)
        if not transformers and digest(bodies["B1"]) != source["requests"]["A3"]["body_sha256"]:
            raise ValueError("B1 must exactly match A3")
        row = {
            "pdf": path.name,
            "pdf_page": number,
            "pdf_sha256": doc.sha256,
            "image_sha256": digest(png),
            "preparation": selection,
            "ocr_producer_sha256": (
                provider.identity.identity_hash if selection != "native" else None
            ),
            "layout_rules_sha256": pinned.layout.algorithm_sha256,
            "reading_count": len(page["readings"]),
            "readings_with_alternatives": sum(bool(x["alternate_texts"]) for x in page["readings"]),
            "requests": {},
        }
        for arm, body in bodies.items():
            (private / f"{path.stem}-{arm}.json").write_bytes(body)
            supplement = json.loads(body)["input"][0]["content"][0]
            text = supplement.get("text", "").encode()
            row["requests"][arm] = {
                "body_sha256": digest(body),
                "body_bytes": len(body),
                "source_projection_sha256": digest(text),
                "source_projection_bytes": len(text),
            }
        rows.append(row)
    first, second = ("Delta", "Rex") if transformers else ("Schneider", "Siemens")
    return {
        "version": "f1b3-investigation-b-transformers-v1"
        if transformers
        else "f1b3-investigation-b-v1",
        "gold_sha256": gold_sha,
        "a_manifest_sha256": digest((HERE / "a-preflight.json").read_bytes()),
        "provider_calls": 0,
        "max_calls": 12,
        "hard_cap_usd": "6.60",
        "retries": 0,
        "orders": {
            first: [ARMS, ("B3", "B2", "B1")],
            second: [("B2", "B3", "B1"), ("B1", "B3", "B2")],
        },
        "pages": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("rasters", type=Path)
    parser.add_argument("private", type=Path)
    parser.add_argument("--transformers", action="store_true")
    args = parser.parse_args()
    args.private.mkdir(mode=0o700, exist_ok=True)
    if args.private.is_symlink() or args.private.stat().st_mode & 0o077:
        raise ValueError("Exact request bodies require a private directory")
    provider = TesseractProvider("/usr/bin/tesseract", "/usr/share/tesseract-ocr/5/tessdata")
    result = prepare(
        args.source_dir, args.rasters, args.private, provider, transformers=args.transformers
    )
    (args.private / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
