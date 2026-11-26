"""Verify F1-B gold and score source-local Stage 1 observations offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Self

import pymupdf
from pydantic import BaseModel, ConfigDict, Field, model_validator

from powerforge_engineering_model.enums import EquipmentType
from powerforge_extraction.stage_contracts import Qualification, TagState

HERE = Path(__file__).resolve().parent
EVALS = HERE.parents[1]
SOURCE_GOLD = HERE.parent / "f1a" / "ground_truth"
EXPECTED = {
    "delta-transformer-drawing.pdf": 1,
    "eaton-panel-drawing.pdf": 1,
    "rex-transformer-drawing.pdf": 1,
    "schneider-panel-drawing.pdf": 1,
    "siemens-panel-drawing.pdf": 1,
    "simson-generator-drawing.pdf": 2,
}
Box = tuple[int, int, int, int]
Region = tuple[float, float, float, float]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Anchor(Strict):
    id: str = Field(min_length=1)
    box: Box
    source_refs: tuple[str, ...] = ()
    note: str = Field(min_length=1)
    position: str | None = None


class Occurrence(Anchor):
    registry_type: EquipmentType | None
    qualification: Qualification
    tag_state: TagState
    tag: str | None
    tag_ref: str | None = None
    alternate_boxes: tuple[Box, ...] = ()

    @model_validator(mode="after")
    def tag_consistency(self) -> Self:
        if (self.tag_state == "PRESENT") != bool(self.tag and self.tag.strip()):
            raise ValueError("present tags require their exact source literal")
        if self.tag_ref is not None and self.tag_state != "PRESENT":
            raise ValueError("only a present tag may have a tag reading")
        return self


class ExceptionAnchor(Anchor):
    kind: Literal["PROVISION", "AGGREGATE", "COMPONENT_OR_CONTEXT", "AMBIGUOUS"]
    quantity: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def aggregate_quantity(self) -> Self:
        if (self.kind == "AGGREGATE") != (self.quantity is not None):
            raise ValueError("aggregate requires a printed count")
        return self


class Page(Strict):
    pdf_page: int = Field(ge=1)
    frame: tuple[int, int]
    preparation: Literal["native", "hybrid_300", "hybrid_300_line_removal"]
    occurrences: tuple[Occurrence, ...]
    exceptions: tuple[ExceptionAnchor, ...]

    @model_validator(mode="after")
    def locations(self) -> Self:
        width, height = self.frame
        ids = set()
        for anchor in (*self.occurrences, *self.exceptions):
            if anchor.id in ids:
                raise ValueError(f"duplicate page-local identifier: {anchor.id}")
            ids.add(anchor.id)
            for x0, y0, x1, y1 in (anchor.box, *getattr(anchor, "alternate_boxes", ())):
                if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                    raise ValueError(f"outside the upright page frame: {anchor.id}")
        return self


class Document(Strict):
    pdf: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_fixture_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pages: tuple[Page, ...] = Field(min_length=1)


class Gold(Strict):
    version: Literal["f1b-occurrence-gold-v1"]
    development: tuple[Document, ...]
    structural_control: tuple[Document, ...]
    synthetic_holdout: tuple[Document, ...]


class Observation(Strict):
    local_ref: str = Field(min_length=1)
    registry_type: EquipmentType | None
    qualification: Qualification
    tag_state: TagState
    tag: str | None
    equipment_regions: tuple[Region, ...] = Field(max_length=384)
    resolved_equipment_fragments: int = Field(ge=0)
    approximate_equipment_fragments: int = Field(ge=0)
    unresolved_equipment_fragments: int = Field(ge=0)
    resolved_tag_fragments: int = Field(default=0, ge=0)
    approximate_tag_fragments: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        for x0, y0, x1, y1 in self.equipment_regions:
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("invalid normalized source region")
        return self


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def annotation_index(page):
    lookup = {region["id"]: region for region in page["regions"]}
    for table in page["tables"]:
        for cell in table["cells"]:
            lookup[f"{table['id']}/{cell['row']}/{cell['column']}"] = cell
    return lookup


def read_gold() -> Gold:
    return Gold.model_validate_json((HERE / "occurrence-gold.json").read_bytes())


def check_corpus(gold: Gold, source_dir: Path) -> None:
    if {doc.pdf: len(doc.pages) for doc in gold.development} != EXPECTED:
        raise ValueError("development gold must cover all six approved original PDFs")
    if len(gold.development) != len(EXPECTED):
        raise ValueError("duplicate development PDFs")
    approved_source_pages = set()
    for split, documents in (
        ("development", gold.development),
        ("structural_control", gold.structural_control),
        ("synthetic_holdout", gold.synthetic_holdout),
    ):
        for doc in documents:
            path = (source_dir if split == "development" else EVALS) / doc.pdf
            data = path.read_bytes()
            if digest(data) != doc.sha256:
                raise ValueError(f"source PDF hash differs for {doc.pdf}")
            source_gold = None
            if split == "development":
                fixture = (SOURCE_GOLD / Path(doc.pdf).with_suffix(".json")).read_bytes()
                source_gold = json.loads(fixture)
                if (
                    digest(fixture) != doc.source_fixture_sha256
                    or source_gold["sha256"] != doc.sha256
                ):
                    raise ValueError(f"source-level gold binding differs for {doc.pdf}")
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if source_gold and [p.pdf_page for p in doc.pages] != list(range(1, len(pdf) + 1)):
                    raise ValueError(f"incomplete approved PDF coverage for {doc.pdf}")
                for page in doc.pages:
                    identity = (doc.sha256, page.pdf_page)
                    if identity in approved_source_pages:
                        raise ValueError(f"evaluation splits overlap: {doc.pdf} p{page.pdf_page}")
                    approved_source_pages.add(identity)
                    physical = pdf[page.pdf_page - 1].rect
                    if abs(page.frame[0] * physical.height / physical.width - page.frame[1]) > 1:
                        raise ValueError(f"page frame differs from original: {doc.pdf}")
                    if source_gold:
                        source_page = source_gold["pages"][page.pdf_page - 1]
                        if tuple(source_page["frame"]) != page.frame:
                            raise ValueError(
                                "expected coordinates must use the source fixture frame"
                            )
                        lookup = annotation_index(source_page)
                        for anchor in (*page.occurrences, *page.exceptions):
                            if not anchor.source_refs or any(
                                ref not in lookup for ref in anchor.source_refs
                            ):
                                raise ValueError(
                                    f"invalid approved source-reference links: {anchor.id}"
                                )
                        for item in page.occurrences:
                            if item.tag_ref and (
                                item.tag_ref not in item.source_refs
                                or item.tag not in lookup[item.tag_ref]["text"]
                            ):
                                raise ValueError(
                                    f"tag literal missing from cited source: {item.id}"
                                )


def region(box: Box, frame: tuple[int, int]) -> Region:
    x0, y0, x1, y1 = box
    width, height = frame
    return x0 / width, y0 / height, x1 / width, y1 / height


def supports(fragment: Region, anchor: Region) -> bool:
    """Require local evidence. A whole-page or shared-row citation earns no location credit."""
    x0, y0, x1, y1 = fragment
    a, b, c, d = anchor
    area = (x1 - x0) * (y1 - y0)
    if area > 2 * (c - a) * (d - b):
        return False
    overlap = max(0, min(x1, c) - max(x0, a)) * max(0, min(y1, d) - max(y0, b))
    return a <= (x0 + x1) / 2 < c and b <= (y0 + y1) / 2 < d and overlap >= 0.60 * area


def score(page: Page, observations: tuple[Observation, ...]) -> dict:
    """Occurrence matching uses evidence geometry only. Conflicting matches abstain."""
    anchors = {
        item.id: tuple(region(box, page.frame) for box in (item.box, *item.alternate_boxes))
        for item in page.occurrences
    }
    exceptions = {item.id: region(item.box, page.frame) for item in page.exceptions}
    occurrence_by_id = {item.id: item for item in page.occurrences}
    exception_by_id = {item.id: item for item in page.exceptions}
    rows = {}
    candidates = defaultdict(list)
    assembly_tags = {
        item.tag for item in page.occurrences if item.registry_type == EquipmentType.BUS
    }
    for obs in observations:
        if obs.local_ref in rows:
            raise ValueError(f"duplicate admitted reference {obs.local_ref}")
        matches = [
            key
            for key, boxes in anchors.items()
            if any(supports(evidence, box) for evidence in obs.equipment_regions for box in boxes)
        ]
        excluded = [
            key
            for key, box in exceptions.items()
            if any(supports(evidence, box) for evidence in obs.equipment_regions)
        ]
        row = dict(
            outcome="UNVERIFIED_OBSERVATION",
            candidates=matches,
            exclusions=excluded,
            resolved_equipment_fragments=obs.resolved_equipment_fragments,
            approximate_equipment_fragments=obs.approximate_equipment_fragments,
            unresolved_equipment_fragments=obs.unresolved_equipment_fragments,
            resolved_tag_fragments=obs.resolved_tag_fragments,
            approximate_tag_fragments=obs.approximate_tag_fragments,
            assembly_tag_on_branch=obs.registry_type
            in (EquipmentType.LV_BREAKER, EquipmentType.HV_BREAKER)
            and obs.tag is not None
            and obs.tag in assembly_tags,
        )
        rows[obs.local_ref] = row
        if len(matches) == 1 and not excluded:
            candidates[matches[0]].append(obs)
        elif matches:
            row["outcome"] = "AMBIGUOUS_SOURCE_ASSOCIATION"
        elif excluded:
            kinds = {exception_by_id[key].kind for key in excluded}
            row["outcome"] = (
                next(iter(kinds)) if len(kinds) == 1 else "AMBIGUOUS_SOURCE_ASSOCIATION"
            )
            row["provision_asserted_installed"] = (
                "PROVISION" in kinds and obs.qualification == "INSTALLED"
            )
    credited = {}
    duplicate_extras = 0
    for key, competing in candidates.items():
        truth = occurrence_by_id[key]
        duplicate_extras += len(competing) - 1
        fields = defaultdict(set)
        for obs in competing:
            dispositions = dict(
                correct_type=obs.registry_type == truth.registry_type,
                correct_tag_state=obs.tag_state == truth.tag_state,
                correct_tag=obs.tag_state == truth.tag_state and obs.tag == truth.tag,
                correct_qualification=obs.qualification == truth.qualification,
            )
            for field, correct in dispositions.items():
                fields[field].add(correct)
            rows[obs.local_ref].update(
                outcome="MATCHED" if len(competing) == 1 else "DUPLICATE_OCCURRENCE_CLAIM",
                occurrence=key,
                **dispositions,
            )
        credited[key] = {
            field: next(iter(outcomes)) if len(outcomes) == 1 else None
            for field, outcomes in fields.items()
        }
    tp = len(credited)
    # Human review is needed for ambiguous engineering references. Keep them
    # separate from both strict unexpected and credited observations.
    excluded = sum(r["outcome"] == "AMBIGUOUS" for r in rows.values())
    precision_denominator = len(rows) - excluded
    precision = tp / precision_denominator if precision_denominator else None
    recall = tp / len(anchors) if anchors else None
    return dict(
        expected=len(anchors),
        observed=len(rows),
        matched=tp,
        duplicate_extras=duplicate_extras,
        pending_adjudication=excluded,
        strict_precision=precision,
        strict_recall=recall,
        strict_f1=2 * precision * recall / (precision + recall)
        if precision and recall
        else (0.0 if precision is not None and recall is not None else None),
        outcomes=dict(Counter(row["outcome"] for row in rows.values())),
        missing=sorted(anchors.keys() - credited.keys()),
        field_accuracy_by_occurrence=credited,
        observations=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument(
        "--observations",
        type=Path,
        help="Restricted prelocalized observation JSON for one pinned document/page",
    )
    args = parser.parse_args()
    gold = read_gold()
    check_corpus(gold, args.source_dir)
    if args.observations:
        sample = json.loads(args.observations.read_text())
        pages = [
            page
            for docs in (gold.development, gold.structural_control, gold.synthetic_holdout)
            for doc in docs
            if doc.sha256 == sample["source_sha256"]
            for page in doc.pages
            if page.pdf_page == sample["pdf_page"]
        ]
        if len(pages) != 1:
            parser.error("observations must bind exactly one pinned evaluation page")
        items = tuple(
            Observation.model_validate_json(json.dumps(item)) for item in sample["observations"]
        )
        print(json.dumps(score(pages[0], items), indent=2))
        return
    for name in ("development", "structural_control", "synthetic_holdout"):
        pages = [page for doc in getattr(gold, name) for page in doc.pages]
        print(
            f"{name}: {len(pages)} pages, {sum(len(p.occurrences) for p in pages)} occurrences, "
            f"{sum(len(p.exceptions) for p in pages)} exception anchors"
        )


if __name__ == "__main__":
    main()
