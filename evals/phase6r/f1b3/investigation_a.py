"""Reproduce and fingerprint the proposed Investigation A bodies without transport."""

import argparse
import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Annotated

from occurrence_eval import check_corpus, read_gold
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from extraction_worker.spatial_evaluation import render
from powerforge_extraction.extraction_profile import structured_schema
from powerforge_extraction.provider_body import encoded_body
from powerforge_extraction.stage_contracts import equipment_catalog

HERE = Path(__file__).resolve().parent
ARMS = ("A1", "A2", "A3")
PAGES = ("schneider-panel-drawing.pdf", "siemens-panel-drawing.pdf")
ARM_ORDERS = (ARMS, ARMS[::-1])
OBJECTIVE = (
    "Identify the supplied equipment shown on this page. List each distinct source occurrence "
    "and state its equipment type and its equipment tag if shown. Describe its position or "
    "source identifier briefly so another reader can tell which occurrence you mean. "
    "Exclude empty prepared spaces, unselected alternatives, generic legends, and equipment "
    "mentioned only for reference. Use engineering context when the type is not stated. "
    "Do not treat schedule positions or model numbers as equipment tags."
)
MODEL = "gpt-6-luna"
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 100


class Equipment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    identification: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
    ]
    type: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
        | None
    )
    tag: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
        | None
    )


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    equipment: list[Equipment] = Field(max_length=128)


def digest(data):
    return sha256(data).hexdigest()


def checked_gold(source_dir):
    """Reuse verified source anchors, applying a separate, pinned supplied-scope fixture."""
    previous = read_gold()
    check_corpus(previous, source_dir)
    raw = (HERE / "recognition-gold-v1.json").read_bytes()
    fixture = json.loads(raw)
    if fixture["anchor_fixture_sha256"] != digest(
        (HERE.parent / "f1b" / "occurrence-gold.json").read_bytes()
    ):
        raise ValueError("F1-B1 anchor fixture changed")
    if fixture["documents"].keys() != {document.pdf for document in previous.development}:
        raise ValueError("Revised fixture must cover exactly the development documents")
    for document in previous.development:
        rule = fixture["documents"][document.pdf]
        anchors = {
            f"{page.pdf_page}/{item.id}": item
            for page in document.pages
            for item in page.occurrences
        }
        excluded = rule.get("additional_exclusions", {})
        if not excluded.keys() <= anchors.keys():
            raise ValueError("Scope exclusion has no pinned source occurrence")
        supplied = anchors.keys() - excluded.keys()
        if not rule.get("tag_overrides", {}).keys() <= supplied:
            raise ValueError("Tag override does not name supplied equipment")
        memberships = set()
        for config in rule["configurations"]:
            members = config["members"]
            if (
                not members
                or len(set(members)) != len(members)
                or memberships.intersection(members)
                or not set(members) <= supplied
                or not config["basis"].strip()
                or config["equivalence"]
                not in ({"single"} if len(members) == 1 else {"established", "unresolved"})
            ):
                raise ValueError("Invalid configuration membership or equivalence")
            members = [anchors[member] for member in members]
            if len({(item.registry_type, item.tag) for item in members}) != 1:
                raise ValueError("Configuration contains different types or tags")
            memberships.update(config["members"])
        if memberships != supplied:
            raise ValueError("Missing configuration expectation")
    return previous, fixture, digest(raw)


def build_body(arm, png):
    if arm not in ARMS:
        raise ValueError("Unknown Investigation A arm")
    if arm == "A1":
        suffix = "\nReply in plain language, using a short list."
    else:
        suffix = (
            "\nReturn one equipment item per occurrence. Use null for an unavailable type or tag."
        )
    if arm == "A3":
        suffix += (
            "\nFor type, use the exact key from the supported equipment catalog below. "
            "If none applies, use null.\n"
        )
        suffix += "\n".join(
            f"{item.key} | {item.name} | {item.description}" for item in equipment_catalog()
        )
    body = {
        "model": MODEL,
        "instructions": OBJECTIVE + suffix,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "detail": "high",
                        "image_url": "data:image/png;base64,"
                        + base64.b64encode(png).decode("ascii"),
                    }
                ],
            }
        ],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "service_tier": "default",
        "store": False,
    }
    if arm != "A1":
        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": "f1b3_recognition_a_v1",
                "strict": True,
                "schema": structured_schema(Reply.model_json_schema()),
            }
        }
    return body


def score_review(reviews, supplied, exclusions):
    """Summarize human-adjudicated rows without guessing positions or semantic matches.

    Each row is (source anchor or None, type correct, tag correct). An unresolved row
    carries None for its anchor. Evaluation evidence and grouping are scored separately.
    """
    matched = set()
    counts = dict.fromkeys(
        (
            "supplied_detected",
            "missing_supplied",
            "duplicate_claims",
            "prepared_space",
            "reference_only",
            "other_excluded",
            "unresolved",
            "classification_correct",
            "tag_correct",
        ),
        0,
    )
    for anchor, type_correct, tag_correct in reviews:
        if anchor is None:
            counts["unresolved"] += 1
        elif anchor in exclusions:
            category = {
                "PROVISION": "prepared_space",
                "REFERENCE_ONLY": "reference_only",
            }.get(exclusions[anchor], "other_excluded")
            counts[category] += 1
        elif anchor not in supplied:
            raise ValueError("Unknown source anchor in adjudication")
        elif anchor in matched:
            counts["duplicate_claims"] += 1
        else:
            matched.add(anchor)
            counts["classification_correct"] += int(type_correct)
            counts["tag_correct"] += int(tag_correct)
    counts["supplied_detected"] = len(matched)
    counts["missing_supplied"] = len(supplied - matched)
    return counts


def preflight(source_dir):
    prior, gold, gold_sha = checked_gold(source_dir)
    pages = []
    exact_specs = {}
    for name in PAGES:
        document = next(item for item in prior.development if item.pdf == name)
        path = source_dir / name
        data = path.read_bytes()
        if digest(data) != document.sha256:
            raise ValueError("Source changed after corpus verification")
        page = render(path, data, 1)
        png = page.analysis_png
        requests = {}
        for arm in ARMS:
            body = build_body(arm, png)
            body_bytes = encoded_body(body)
            requests[arm] = {
                "body_sha256": digest(body_bytes),
                "body_bytes": len(body_bytes),
                "prompt_sha256": digest(body["instructions"].encode()),
                "schema_sha256": digest(encoded_body(body["text"]["format"]["schema"]))
                if "text" in body
                else None,
            }
            exact_specs[arm] = {
                "instructions": body["instructions"],
                "text": body.get("text"),
            }
        pages.append(
            {
                "pdf": name,
                "pdf_page": 1,
                "pdf_sha256": document.sha256,
                "analysis_png_sha256": digest(png),
                "raster_px": [page.width_px, page.height_px],
                "effective_dpi": page.effective_dpi,
                "native_characters_on_page": page.native_text_char_count,
                "source_projection": "canonical-analysis-png-only",
                "source_projection_sha256": digest(png),
                "supplied_occurrences": len(document.pages[0].occurrences)
                - len(gold["documents"][name].get("additional_exclusions", {})),
                "requests": requests,
            }
        )
    return {
        "version": "f1b3-investigation-a-v1",
        "mode": "offline_preflight",
        "gold_sha256": gold_sha,
        "provider_calls": 0,
        "model": MODEL,
        "service_tier": "default",
        "reasoning_effort_requested": None,
        "detail": "high",
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "automatic_retries": 0,
        "arm_orders": ARM_ORDERS,
        "initial_calls": 6,
        "maximum_calls": 12,
        "hard_cap_usd": "6.60",
        "pages": pages,
        "arm_specs": exact_specs,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = preflight(args.source_directory)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
