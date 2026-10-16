from datetime import datetime
from enum import Enum
from typing import Any, Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict


class CaseState(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    ELIGIBLE = "eligible"
    HUMAN_REVIEW = "human_review"
    CLAIM_READY = "claim_ready"
    SUBMITTED = "submitted"
    DISPUTED = "disputed"
    DEFENDED = "defended"
    ACCEPTED = "accepted"
    VERIFIED = "verified"
    CLOSED = "closed"


ShortText = Annotated[str, Field(max_length=2000)]


class SafeInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_max_length=4000)


class MaintenanceWindow(SafeInput):
    start: datetime
    end: datetime
    description: str


class EvidenceItem(BaseModel):
    id: str
    type: str
    source: str
    timestamp: datetime | None = None
    summary: str
    value: str | float | int | None = None
    source_page: int | None = None
    source_section: str | None = None


class SLAClause(SafeInput):
    id: str
    title: str
    service: str
    response_minutes: int | None = Field(default=None, ge=1, le=525600)
    repair_minutes: int | None = Field(default=None, ge=1, le=525600)
    rate_per_eligible_hour_usd: float = Field(gt=0, le=1000000000)
    cap_usd: float = Field(gt=0, le=1000000000)
    claim_window_days: int = Field(ge=1, le=3650)
    exclusions: list[ShortText] = Field(default_factory=list, max_length=32)
    source_page: int | None = None
    source_section: str | None = None
    source_quote: str | None = None


class VendorContract(SafeInput):
    id: str = Field(min_length=1, max_length=160)
    customer: str
    vendor: str
    effective_date: datetime
    sla: SLAClause
    source_filename: str | None = None
    source_text_sha256: str | None = None
    source_document_id: str | None = None
    source_file_sha256: str | None = None


class InfrastructureIncident(SafeInput):
    id: str = Field(min_length=1, max_length=160)
    service: str
    vendor: str
    start: datetime
    end: datetime
    severity: str
    telemetry: dict[ShortText, float | ShortText] = Field(max_length=64)
    ticket_opened_at: datetime
    vendor_acknowledged_at: datetime
    maintenance_windows: list[MaintenanceWindow] = Field(default_factory=list, max_length=25)
    notes: list[ShortText] = Field(default_factory=list, max_length=64)


class EntitlementResult(BaseModel):
    eligible: bool
    eligible_hours: float
    gross_amount_usd: float
    capped_amount_usd: float
    exclusion_applies: bool
    exclusion_reason: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ModelAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    decision: Literal['supported', 'needs_review', 'not_supported']
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=64)
    contradictions: list[str] = Field(default_factory=list, max_length=32)
    exclusion_analysis: list[str] = Field(default_factory=list, max_length=32)


class ReasoningAssessment(ModelAssessment):
    # Application-created provenance, never accepted from model output.
    inference: dict[str, Any] | None = None


class EvidenceNode(BaseModel):
    id: str
    kind: str
    label: str
    status: str = "supporting"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdge(BaseModel):
    source: str
    target: str
    relation: str


class EvidenceGraph(BaseModel):
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)


class ClaimChronologyItem(BaseModel):
    at: datetime
    label: str
    source_id: str


class ClaimPackage(BaseModel):
    case_id: str
    claimant: str
    respondent: str
    contract_id: str
    incident_id: str
    amount_usd: float
    clause_ids: list[str]
    chronology: list[ClaimChronologyItem]
    evidence_ids: list[str]
    factual_basis: str
    requested_remedy: str
    generated_at: datetime
    approval_required: bool = False


class ContractIngestionResult(BaseModel):
    contract: VendorContract
    extracted_text_preview: str
    pages: int
    warnings: list[str] = Field(default_factory=list)
    document_id: str | None = None


class CaseEvent(BaseModel):
    at: datetime
    state: CaseState
    message: str


class ClaimCase(BaseModel):
    id: str
    incident_id: str
    contract_id: str
    state: CaseState
    confidence: float
    amount_usd: float = 0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    timeline: list[CaseEvent] = Field(default_factory=list)
    human_review_reason: str | None = None
    reasoning: ReasoningAssessment | None = None
    model_assessment: ModelAssessment | None = None
    evidence_graph: EvidenceGraph | None = None
    claim_package: ClaimPackage | None = None
    version: int = 0
    auto_run: bool = False
    contract_snapshot: VendorContract | None = None
    incident_snapshot: InfrastructureIncident | None = None
    vendor_claim_id: str | None = None
    counter_investigation: ReasoningAssessment | None = None
    counter_mode: str | None = None
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)
    reconciliation: dict[str, Any] | None = None
    source: Literal['demo', 'manual'] = 'demo'
    review_approved: bool = False
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    amendments: list[dict[str, Any]] = Field(default_factory=list)
