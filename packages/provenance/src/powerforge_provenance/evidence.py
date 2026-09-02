from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    """Traceability for an extracted or reconciled value.

    Persistence of evidence rows is a later phase; this is the shared contract.
    """

    document_id: str
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    artifact_id: str | None = None
    extracted_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_method: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    provider: str | None = None
