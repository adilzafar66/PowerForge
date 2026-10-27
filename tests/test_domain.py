from powerforge_ai.providers import DocumentClassificationResult, StructuredExtractionResult
from powerforge_document_model import DocumentClassification
from powerforge_engineering_model import EquipmentType, InformationState, VerificationState
from powerforge_extraction import ExtractionMethod
from powerforge_provenance import EvidenceRef
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind
from powerforge_validation import RuleRegistry


def test_equipment_types_cover_initial_model() -> None:
    assert EquipmentType.TWO_WINDING_TRANSFORMER == "TWO_WINDING_TRANSFORMER"
    assert EquipmentType.LV_BREAKER == "LV_BREAKER"
    assert len(EquipmentType) == 20


def test_verification_states_are_explicit() -> None:
    assert VerificationState.AI_EXTRACTED != VerificationState.ENGINEER_VERIFIED
    assert {state.value for state in VerificationState} == {
        "UNVERIFIED",
        "AI_EXTRACTED",
        "SYSTEM_VALIDATED",
        "ENGINEER_REVIEWED",
        "ENGINEER_VERIFIED",
    }


def test_information_states_are_not_only_null() -> None:
    assert set(InformationState.__members__) == {
        "PRESENT",
        "MISSING",
        "NOT_APPLICABLE",
        "NOT_POPULATED",
        "CONFLICTING",
    }
    assert InformationState.NOT_POPULATED in InformationState


def test_document_classifications_include_unknown() -> None:
    assert DocumentClassification.SINGLE_LINE_DIAGRAM in DocumentClassification
    assert DocumentClassification.UNKNOWN in DocumentClassification


def test_extraction_and_topology_vocabularies() -> None:
    assert ExtractionMethod.AI_VISION == "AI_VISION"
    assert set(ModelNodeKind) == {"EQUIPMENT_TERMINAL", "ELECTRICAL_NODE"}
    assert set(ConnectionKind) == {"ELECTRICAL", "GROUNDING", "OTHER"}
    assert set(ConnectionDirection) == {"UNDIRECTED", "NOMINAL_FROM_TO"}


def test_evidence_ref_requires_document() -> None:
    evidence = EvidenceRef(document_id="doc-1", page_number=4, confidence=0.96)
    assert evidence.document_id == "doc-1"
    assert evidence.page_number == 4


def test_validation_registry_starts_empty() -> None:
    assert RuleRegistry().names() == ()


def test_document_classification_result_is_provider_neutral() -> None:
    result = DocumentClassificationResult(
        predicted_type="TRANSFORMER_SHOP_DRAWING",
        confidence_score=0.91,
        rationale="Pages show transformer outline drawings.",
    )
    assert result.predicted_type == "TRANSFORMER_SHOP_DRAWING"
    assert result.confidence_score == 0.91
    assert "confidence_band" not in DocumentClassificationResult.model_fields


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
