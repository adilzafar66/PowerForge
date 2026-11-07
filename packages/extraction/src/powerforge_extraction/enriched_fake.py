"""Clearly synthetic fixture execution for the enhanced worker path; no accuracy claim."""

import json
import re

from powerforge_ai.extraction import ErrorCode, ExecutionUsage, ExtractionResponse, ProviderFailure


class FakeEnrichedProvider:
    def __init__(self, scenario="success"):
        self.scenario = scenario

    def execute(self, request):
        if self.scenario == "transient" and getattr(request, "attempt_number", 1) == 1:
            raise ProviderFailure(ErrorCode.UNAVAILABLE)
        if self.scenario == "invalid":
            raise ProviderFailure(ErrorCode.INVALID)
        if self.scenario == "slow":
            import time

            time.sleep(3)
        if self.scenario == "permanent":
            raise ProviderFailure(ErrorCode.AUTH)
        if self.scenario == "interrupted":
            from powerforge_extraction.fake import SimulatedWorkerInterruption

            raise SimulatedWorkerInterruption()
        source = json.loads(request.text)
        readings = {r["ref"]: r["raw_text"] for r in source["readings"]}

        def text(refs):
            return " ".join(readings[r] for r in refs)

        def anchor(refs):
            return [dict(source_ref="spatial_readings", reading_refs=refs)]

        uncertainty = dict(ambiguous=False, ambiguity_reason=None)
        payload = dict(schema_version=request.schema_version, overflowed=False)
        empty = self.scenario == "empty"
        if request.stage == "EQUIPMENT_RECOGNITION":
            payload["equipment"] = []
            for i, line in enumerate(source["lines"] if not empty else []):
                raw = text(line["reading_refs"])
                if re.search(r"transformer|breaker|cable", raw, re.I) and ":" not in raw:
                    tag = re.search(r"\b[A-Za-z]+-\d+\b", raw)
                    payload["equipment"].append(
                        dict(
                            local_ref=f"e{i}",
                            raw_expression=raw,
                            anchors=anchor(line["reading_refs"]),
                            observed_tag=tag[0] if tag else None,
                            observed_name=None,
                            proposed_equipment_type=None,
                            **uncertainty,
                        )
                    )
        elif request.stage == "ATTRIBUTE_EXTRACTION":
            payload["attributes"] = []
            mentions = json.loads(request.upstream_context)["equipment"]
            for i, line in enumerate(source["lines"] if not empty else []):
                raw = text(line["reading_refs"])
                match = re.fullmatch(r"([^:]+):\s*([+-]?[\d.]+)\s*([A-Za-z%]+)?", raw)
                if match:
                    payload["attributes"].append(
                        dict(
                            local_ref=f"a{i}",
                            raw_expression=raw,
                            anchors=anchor(line["reading_refs"]),
                            equipment_ref=mentions[0]["local_ref"] if len(mentions) == 1 else None,
                            source_label=match[1],
                            raw_value=match[2],
                            raw_unit=match[3],
                            proposed_equipment_type=None,
                            proposed_attribute_key=None,
                            **uncertainty,
                        )
                    )
        elif request.stage == "TABLE_RECONSTRUCTION":
            payload["tables"] = []
            for i, table in enumerate(source["tables"] if not empty else []):
                aliases = {c["ref"]: f"c{j}" for j, c in enumerate(table["cells"])}
                cells = [
                    dict(
                        local_ref=aliases[c["ref"]],
                        spatial_cell_ref=c["ref"],
                        row=c["row"],
                        column=c["column"],
                        row_span=c["row_span"],
                        column_span=c["column_span"],
                        state="VALUE" if c["reading_refs"] else "BLANK",
                        raw_text=text(c["reading_refs"]),
                        header_role="COLUMN" if c["header_role"] == "COLUMN" else "NONE",
                        header_refs=[aliases[h] for h in c["headers"]],
                        anchors=anchor(c["reading_refs"])
                        if c["reading_refs"]
                        else [dict(source_ref="analysis_image", reading_refs=[])],
                        **uncertainty,
                    )
                    for c in table["cells"]
                ]
                caption = table["captions"]
                payload["tables"].append(
                    dict(
                        local_ref=f"t{i}",
                        spatial_table_ref=table["ref"],
                        proposed_kind="EQUIPMENT_ROWS",
                        title=dict(
                            local_ref="title",
                            raw_text=text(caption),
                            anchors=anchor(caption),
                            **uncertainty,
                        )
                        if caption
                        else None,
                        notes=[],
                        rows=[f"r{r}" for r in range(table["rows"])],
                        columns=[f"col{c}" for c in range(table["columns"])],
                        cells=cells,
                        anchors=[dict(source_ref="analysis_image", reading_refs=[])],
                        truncated=False,
                        truncation_reason=None,
                        **uncertainty,
                    )
                )
        else:
            payload.update(equipment=[], attributes=[])
            for table in json.loads(request.upstream_context)["tables"] if not empty else []:
                obs = table["observation"]
                for cell in obs["cells"]:
                    if cell["row"] == 0 or cell["column"] != 0 or not cell["raw_text"]:
                        continue
                    ref = "e" + str(len(payload["equipment"]))
                    tag = re.search(r"\b[A-Za-z]+-\d+\b", cell["raw_text"])
                    payload["equipment"].append(
                        dict(
                            local_ref=ref,
                            table_ref=table["table_ref"],
                            raw_expression=cell["raw_text"],
                            source_refs=[cell["local_ref"]],
                            observed_tag=tag[0] if tag else None,
                            observed_name=None,
                            proposed_equipment_type=None,
                            **uncertainty,
                        )
                    )
                    for value in obs["cells"]:
                        if (
                            value["row"] != cell["row"]
                            or value["column"] == 0
                            or not value["raw_text"]
                        ):
                            continue
                        match = re.fullmatch(r"([+-]?[\d.]+)\s*([A-Za-z%]+)?", value["raw_text"])
                        if not match:
                            continue
                        label = next(
                            (
                                c["raw_text"]
                                for c in obs["cells"]
                                if c["local_ref"] in value["header_refs"]
                            ),
                            None,
                        )
                        payload["attributes"].append(
                            dict(
                                local_ref=f"a{len(payload['attributes'])}",
                                table_ref=table["table_ref"],
                                equipment_ref=ref,
                                value_cell_ref=value["local_ref"],
                                label_refs=value["header_refs"],
                                unit_refs=[],
                                qualifier_refs=[],
                                raw_expression=value["raw_text"],
                                source_label=label,
                                raw_value=match[1],
                                raw_unit=match[2],
                                proposed_equipment_type=None,
                                proposed_attribute_key=None,
                                **uncertainty,
                            )
                        )
        result = request.response_model.model_validate(payload)
        return ExtractionResponse[request.response_model](
            result=result, usage=ExecutionUsage(input_tokens=1, output_tokens=1)
        )
