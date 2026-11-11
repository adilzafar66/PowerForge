"""Actual Celery worker with a synthetic Responses transport for enriched Tables."""

import json
from types import SimpleNamespace

from extraction_worker import extraction_tasks
from extraction_worker.celery_app import celery_app as celery_app
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_extraction.enriched_fake import FakeEnrichedProvider
from powerforge_extraction.enriched_observations import RESPONSES, SCHEMAS
from powerforge_extraction.semantic_observations import SemanticTableResponse
from powerforge_extraction.table_reconstruction_v4 import CompactReconstructionResponse
from powerforge_shared.config import get_settings


class Transport:
    def parse(self, **options):
        model = options["text_format"]
        source = json.loads(options["input"][0]["content"][0]["text"])["source"]
        upstream = (
            json.loads(options["input"][1]["content"][0]["text"])["observations"]
            if len(options["input"]) > 1
            else None
        )
        assert options["store"] is False
        if model is CompactReconstructionResponse:
            output = model.model_validate(
                dict(
                    schema_version="table-reconstruction-schema-v3",
                    overflowed=False,
                    partitions=[
                        dict(
                            local_ref=f"t{i}",
                            spatial_table_ref=item["ref"],
                            proposed_kind="EQUIPMENT_ROWS",
                        )
                        for i, item in enumerate(source["tables"])
                    ],
                    reported_tables=[],
                )
            )
        else:
            stage = "TABLE_RECONSTRUCTION" if upstream is None else "TABLE_INTERPRETATION"
            output = (
                FakeEnrichedProvider()
                .execute(
                    SimpleNamespace(
                        stage=stage,
                        text=json.dumps(source),
                        response_model=RESPONSES[stage],
                        schema_version=SCHEMAS[stage],
                        upstream_context=json.dumps(upstream) if upstream is not None else None,
                    )
                )
                .result
            )
            if model is SemanticTableResponse:
                body = output.model_dump(mode="json")
                body["schema_version"] = "table-interpretation-schema-v3"
                for equipment in body["equipment"]:
                    equipment["proposed_equipment_type"] = "TWO_WINDING_TRANSFORMER"
                for value in body["attributes"]:
                    value.update(
                        raw_unit="V",
                        proposed_attribute_key="secondary_voltage",
                        proposed_equipment_type="TWO_WINDING_TRANSFORMER",
                    )
                output = model.model_validate(body)
        return SimpleNamespace(status="completed", output_parsed=output, output=[], usage=None)


def fixture_provider(claim):
    assert claim.profile.key in {"tables-openai-enriched-v3", "tables-openai-enriched-v4"}
    return OpenAIExtractionProvider(
        get_settings(),
        client=SimpleNamespace(responses=Transport()),
        profile=claim.profile,
    )


extraction_tasks.provider_for = fixture_provider
