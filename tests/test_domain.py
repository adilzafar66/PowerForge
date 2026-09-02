from powerforge_ai.providers import StructuredExtractionResult
from powerforge_document_model import DocumentClassification
from powerforge_engineering_model import EquipmentType, InformationState, VerificationState
from powerforge_extraction import ExtractionMethod
from powerforge_provenance import EvidenceRef
from powerforge_topology import NodeKind
from powerforge_validation import RuleRegistry


def test_equipment_types_cover_initial_model() -> None:
    assert EquipmentType.TRANSFORMER == "Transformer"
    assert EquipmentType.BREAKER == "Breaker"
    assert len(EquipmentType) >= 15


def test_verification_states_are_explicit() -> None:
    assert VerificationState.AI_EXTRACTED != VerificationState.ENGINEER_VERIFIED
    assert {state.value for state in VerificationState} == {
        "AI_EXTRACTED",
        "SYSTEM_VALIDATED",
        "ENGINEER_REVIEWED",
        "ENGINEER_VERIFIED",
    }


def test_information_states_are_not_only_null() -> None:
    assert InformationState.MISSING != InformationState.UNKNOWN
    assert InformationState.NOT_EXTRACTED in InformationState


def test_document_classifications_include_unknown() -> None:
    assert DocumentClassification.SINGLE_LINE_DIAGRAM in DocumentClassification
    assert DocumentClassification.UNKNOWN in DocumentClassification


def test_extraction_and_topology_vocabularies() -> None:
    assert ExtractionMethod.AI_VISION == "AI_VISION"
    assert NodeKind.BUS == "bus"


def test_evidence_ref_requires_document() -> None:
    evidence = EvidenceRef(document_id="doc-1", page_number=4, confidence=0.96)
    assert evidence.document_id == "doc-1"
    assert evidence.page_number == 4


def test_validation_registry_starts_empty() -> None:
    assert RuleRegistry().names() == ()


def test_structured_extraction_result_is_provider_agnostic() -> None:
    result = StructuredExtractionResult(
        data={"tag": "T1"},
        provider="example",
        model="example-model",
        model_version="1",
        prompt_version="equipment_extraction_v1",
    )
    assert "tag" in result.data
    assert result.provider == "example"
