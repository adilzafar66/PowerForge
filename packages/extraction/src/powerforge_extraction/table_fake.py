"""Explicit synthetic empty table observations; populated fixtures live only in tests."""

from powerforge_ai.extraction import ExtractionResponse
from powerforge_extraction.fake import FakeExtractionProvider


class FakeTableProvider(FakeExtractionProvider):
    def execute(self, request):
        probe = super().execute(request)
        collections = (
            {"tables": []}
            if request.stage == "TABLE_RECONSTRUCTION"
            else {"equipment": [], "attributes": []}
        )
        return ExtractionResponse[request.response_model](
            result={"schema_version": request.schema_version, "overflowed": False, **collections},
            usage=probe.usage,
        )
