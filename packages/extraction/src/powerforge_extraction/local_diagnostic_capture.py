"""Explicit process-local capture for authorized development reproductions."""

from time import monotonic
from uuid import UUID


class LocalDiagnosticCapture:
    """Use as a context manager in an isolated developer process for one attempt."""

    def __init__(self, unit_id: UUID):
        self.unit_id = unit_id
        self._expires = None
        self._used = False
        self._clear()

    def _clear(self):
        self._projection = None
        self._identities = None
        self._parsed = None
        self._events = []
        self._committed = False
        self._omitted = set()

    def __enter__(self):
        if self._expires is not None or self._used:
            raise RuntimeError("Capture is single-use")
        self._expires = monotonic() + 600
        return self

    def __exit__(self, *_):
        self._clear()
        self._expires = None
        self._used = True

    def _active(self):
        if self._expires is not None and monotonic() < self._expires:
            return True
        self._clear()
        return False

    def bind(self, unit_id: UUID):
        if self._used or unit_id != self.unit_id or not self._active():
            return None
        self._used = True
        return self

    def request(self, projection, schema_version, prompt_sha256):
        if self._active():
            self._identities = (schema_version, prompt_sha256)
            if len(projection.encode()) <= 131_072:
                self._projection = projection
            else:
                self._omitted.add("projection")

    def response(self, parsed):
        if self._active():
            encoded = parsed.model_dump_json()
            if len(encoded.encode()) <= 1_048_576:
                self._parsed = encoded
            else:
                self._omitted.add("parsed_response")

    def observation(self, observation, outcome, *, reason, candidate, association):
        if not self._active():
            return
        if len(self._events) == 1024:
            self._omitted.add("events")
            return
        self._events.append(
            {
                "observation_ref": observation.local_ref,
                "outcome": outcome,
                "reason": reason,
                "output_id": str(candidate.id) if candidate else None,
                "final_equipment_type": getattr(candidate, "equipment_type_key", None),
                "final_attribute_key": getattr(candidate, "attribute_key", None),
                "association_basis": association,
                "structure_basis": getattr(candidate, "diagnostics", {}).get("structure_basis")
                or getattr(getattr(candidate, "layout", None), "metadata", {}).get(
                    "structure_basis"
                ),
                "reading_bases": tuple(
                    getattr(candidate, "diagnostics", {}).get("reading_bases", ())
                ),
                "mapping_basis": getattr(candidate, "diagnostics", {}).get(
                    "mapping_basis", "FROZEN_V1_INTERPRETATION"
                )
                if getattr(candidate, "mapping_status", None) == "MAPPED"
                else None,
            }
        )

    def committed(self):
        self._committed = self._active()

    def inspect(self):
        if not self._active():
            raise RuntimeError("Capture is closed or expired")
        return {
            "work_unit_id": str(self.unit_id),
            "schema_and_prompt_identity": self._identities,
            "source_projection": self._projection,
            "parsed_response": self._parsed,
            "events": tuple(
                {**event, "output_id": event["output_id"] if self._committed else None}
                for event in self._events
            ),
            "omitted": sorted(self._omitted),
        }
