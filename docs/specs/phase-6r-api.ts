// Phase 6R v1 API shapes. These definitions are contract design, outside the app bundle.
export type Id = string;
export type Sha256 = string;
export type DecimalString = string;
export type AIStage = "EQUIPMENT_RECOGNITION" | "ATTRIBUTE_EXTRACTION";
export type Status = "PENDING" | "RUNNING" | "COMPLETED" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED";
export type MappingStatus = "MAPPED" | "UNMAPPED" | "INVALID";
export type Association = "ASSERTED" | "UNCERTAIN" | "UNASSIGNED";
export type TagState = "PRESENT" | "ABSENT" | "UNREADABLE" | "AMBIGUOUS";
export type Qualification = "INSTALLED" | "PROPOSED" | "FUTURE" | "SPARE" | "REFERENCE" | "LEGEND_ONLY" | "UNKNOWN";
export type EvidenceRole = "EQUIPMENT" | "TAG" | "LABEL" | "HEADER" | "VALUE" | "UNIT" | "QUALIFIER" | "CONTEXT";

export interface DocumentSelection {
  revision_document_id: Id;
  pages: number[];
  force_ocr_pages: number[];
}

export interface SourceOption {
  revision_document_id: Id;
  document_id: Id;
  processing_run_id: Id | null;
  pages: Array<{ page_number: number; page_id: Id; available: boolean }>;
}

export interface OperationPreview {
  selection: { documents: DocumentSelection[] };
  review_hash: Sha256;
  expires_at: string;
  documents: Array<{
    revision_document_id: Id;
    page_ids: Id[];
    reusable_run_id: Id | null;
    preparation_required: boolean;
  }>;
  max_provider_calls: number;
  max_ocr_attempts: number;
}

export interface StartOperation {
  selection: OperationPreview["selection"];
  review_hash: Sha256;
  request_key: Id;
  external_processing_consent: true;
}

export interface Operation {
  id: Id;
  status: Status;
  created_at: string;
  documents: Array<{
    revision_document_id: Id;
    run_id: Id;
    preparation_status: Status;
    status: Status;
  }>;
}

export type OperationRetry = { revision_document_id: Id } & (
  | RetryAttempt
  | { stage: "PREPARATION"; page_id: Id; expected_attempt: number }
  | { stage: "RESUME" }
);

export interface RetryAttempt {
  page_id: Id;
  stage: AIStage;
  expected_attempt: number;
  acknowledge_unknown_outcome: boolean;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

export interface EstimatedCost {
  currency: string;
  amount: DecimalString;
  pricing_version: string;
}

export interface Attempt {
  id: Id;
  attempt_number: number;
  stage: AIStage;
  status: Status;
  outcome: "RESULT" | "NO_ELIGIBLE_ATTRIBUTES" | null;
  error_code: string | null;
  retryable: boolean;
  provider_calls: number;
  usage: Usage | null;
  latency_ms: number | null;
  estimated_cost: EstimatedCost | null;
  result_sha256: Sha256 | null;
}

export interface RunSummary {
  id: Id;
  status: Status;
  created_at: string;
  page_count: number;
  pages_completed: number;
  pages_failed: number;
}

export interface PageBinding {
  page_id: Id;
  page_number: number;
  page_image_id: Id;
  processing_run_id: Id;
  preparation_id: Id;
  layout_id: Id;
  page_context_hash: Sha256;
}

export interface RunDetail extends RunSummary {
  document_id: Id;
  registry_version: string;
  profile_sha256: Sha256;
  pages: Array<{
    page_id: Id;
    page_number: number;
    preparation_status: Status;
    binding: PageBinding | null;
    attempts: Attempt[];
  }>;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface CandidateBase {
  id: Id;
  page_id: Id;
  attempt_id: Id;
  mapping_status: MappingStatus;
  reason_code: string | null;
  evidence_ids: Id[];
  conflict: boolean;
}

export interface EquipmentCandidate extends CandidateBase {
  kind: "EQUIPMENT";
  source_description: string;
  registry_type: string | null;
  tag: string | null;
  tag_state: TagState;
  qualification: Qualification;
  raw_qualification: string | null;
}

export type NormalizedValue =
  | { type: "NUMBER" | "INTEGER"; value: DecimalString; unit: string | null }
  | { type: "TEXT" | "ENUM"; value: string; unit: null }
  | { type: "BOOLEAN"; value: boolean; unit: null };

export interface AttributeCandidate extends CandidateBase {
  kind: "ATTRIBUTE";
  equipment_id: Id | null;
  association: Association;
  raw_unmapped: boolean;
  raw_label: string | null;
  raw_value: string;
  raw_unit: string | null;
  qualifiers: string[];
  value_form: "SINGLE" | "RANGE" | "MULTIPLE" | "QUALIFIED";
  proposed_attribute_key: string | null;
  proposed_enum_value: string | null;
  normalized: NormalizedValue | null;
}

export type Candidate = EquipmentCandidate | AttributeCandidate;

export interface Region {
  x: DecimalString;
  y: DecimalString;
  width: DecimalString;
  height: DecimalString;
}

interface EvidenceBase {
  id: Id;
  candidate_id: Id;
  role: EvidenceRole;
  page_id: Id;
  page_image_id: Id;
}

export type Evidence =
  | (EvidenceBase & {
      localization: "RESOLVED";
      modality: "NATIVE_PDF" | "OCR";
      text_artifact_id: Id;
      start: number;
      end: number;
      quote: string;
      regions: Region[];
    })
  | (EvidenceBase & {
      localization: "VISUAL_REPORTED";
      reported_text: string | null;
      region: Region;
    })
  | (EvidenceBase & {
      localization: "UNRESOLVED";
      reason_code: string;
    });
