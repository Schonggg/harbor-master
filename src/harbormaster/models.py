"""Harbormaster domain models.

Official graded schema (Category / EmailVerdict / Submission) is authoritative
for /submit. Bridge models (CaseCard, CourtState, ScoutLabel) remain for the
existing frontend. LLM never writes a match/mismatch verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


# ── Official graded schema ─────────────────────────────────────────────


class Category(str, Enum):
    BL_COMPARISON = "BL_COMPARISON"
    SI_REQUEST = "SI_REQUEST"
    INVOICE_QUERY = "INVOICE_QUERY"
    GENERAL = "GENERAL"
    SPAM = "SPAM"


class ComparisonStatus(str, Enum):
    OK = "OK"
    MISMATCH = "MISMATCH"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReviewReason(str, Enum):
    WRONG_DOC_TYPE = "wrong_doc_type"
    MISSING_ATTACHMENT = "missing_attachment"
    UNREADABLE = "unreadable"
    MISSING_VALUE = "missing_value"


class FieldName(str, Enum):
    SHIPPER = "shipper"
    CONSIGNEE = "consignee"
    NOTIFY_PARTY = "notify_party"
    PORT_OF_LOADING = "port_of_loading"
    PORT_OF_DISCHARGE = "port_of_discharge"
    CONTAINER_COUNT = "container_count"
    GROSS_WEIGHT_KG = "gross_weight_kg"


COMPARE_FIELDS: tuple[str, ...] = tuple(f.value for f in FieldName)
COMPARE_FIELD_SET = frozenset(COMPARE_FIELDS)

# Frontend demo still extracts vessel/voyage; official scoring does not.
DEMO_EXTRA_FIELDS: tuple[str, ...] = ("vessel_voyage", "gross_weight")
DEMO_EMAIL_PREFIX = "demo_"


def is_demo_email_id(email_id: object | None) -> bool:
    """True for the 14-email replay fixtures. Official SDOC ids are `email_NNN`."""
    return str(email_id or "").startswith(DEMO_EMAIL_PREFIX)


def canonical_field_name(name: str) -> str:
    """Map legacy aliases onto the official FieldName enum."""
    key = name.strip().lower().replace(" ", "_")
    aliases = {
        "gross_weight": FieldName.GROSS_WEIGHT_KG.value,
        "gw": FieldName.GROSS_WEIGHT_KG.value,
        "weight": FieldName.GROSS_WEIGHT_KG.value,
        "pol": FieldName.PORT_OF_LOADING.value,
        "pod": FieldName.PORT_OF_DISCHARGE.value,
        "notify": FieldName.NOTIFY_PARTY.value,
        "cnee": FieldName.CONSIGNEE.value,
        "consignor": FieldName.SHIPPER.value,
        "exporter": FieldName.SHIPPER.value,
    }
    return aliases.get(key, key)


class EmailVerdict(BaseModel):
    """One email's graded record. Keys and enums are fixed by the sponsor schema."""

    category: Category
    status: ComparisonStatus | None = None
    review_reason: ReviewReason | None = None
    has_defect: bool = False
    defect_fields: list[str] = Field(default_factory=list)
    decided_by: Literal["rule", "llm"] = "rule"

    @field_validator("defect_fields")
    @classmethod
    def _valid_defect_fields(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for name in v:
            canon = canonical_field_name(name)
            if canon not in COMPARE_FIELD_SET:
                raise ValueError(f"defect_fields contains unknown field: {name!r}")
            if canon not in out:
                out.append(canon)
        return out

    @model_validator(mode="after")
    def _enforce_category_semantics(self) -> EmailVerdict:
        if self.category != Category.BL_COMPARISON:
            object.__setattr__(self, "status", None)
            object.__setattr__(self, "review_reason", None)
            object.__setattr__(self, "has_defect", False)
            object.__setattr__(self, "defect_fields", [])
            return self
        if self.status != ComparisonStatus.NEEDS_REVIEW:
            object.__setattr__(self, "review_reason", None)
        if self.status != ComparisonStatus.MISMATCH:
            object.__setattr__(self, "has_defect", False)
            object.__setattr__(self, "defect_fields", [])
        else:
            object.__setattr__(self, "has_defect", True)
        return self

    def as_submission_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "status": self.status.value if self.status else None,
            "review_reason": self.review_reason.value if self.review_reason else None,
            "has_defect": bool(self.has_defect),
            "defect_fields": list(self.defect_fields),
            "decided_by": self.decided_by,
        }


def blank_verdict(category: Category = Category.GENERAL) -> EmailVerdict:
    return EmailVerdict(category=category)


class Submission(RootModel[dict[str, EmailVerdict]]):
    """Top-level graded payload: {email_id: EmailVerdict, ...}."""

    def email_ids(self) -> list[str]:
        return list(self.root.keys())

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {eid: v.as_submission_dict() for eid, v in self.root.items()}

    def validate_coverage(self, required_ids: list[str]) -> None:
        required = [str(i) for i in required_ids]
        have = set(self.root)
        missing = [i for i in required if i not in have]
        extra = sorted(have - set(required))
        if missing:
            preview = ", ".join(missing[:12])
            more = f" (+{len(missing) - 12} more)" if len(missing) > 12 else ""
            raise ValueError(f"submission missing {len(missing)} email_id(s): {preview}{more}")
        if extra:
            preview = ", ".join(extra[:12])
            more = f" (+{len(extra) - 12} more)" if len(extra) > 12 else ""
            raise ValueError(f"submission has {len(extra)} unexpected email_id(s): {preview}{more}")


# ── Enums (Bridge / court) ─────────────────────────────────────────────


class EvidenceSource(str, Enum):
    TEXT = "text"
    OCR = "ocr"
    VISION = "vision"
    EMAIL_BODY = "email_body"
    ATTACHMENT_META = "attachment_meta"
    RULE = "rule"
    LEDGER = "ledger"


class ScoutLabel(str, Enum):
    BOOKING_CONFIRMATION = "booking_confirmation"
    SHIPPING_INSTRUCTION = "shipping_instruction"
    BILL_OF_LADING = "bill_of_lading"
    AMENDMENT_REQUEST = "amendment_request"
    DISCREPANCY_QUERY = "discrepancy_query"
    INVOICE_OR_CHARGES = "invoice_or_charges"
    OPERATIONAL_NOISE = "operational_noise"
    UNKNOWN = "unknown"


CATEGORY_TO_SCOUT: dict[Category, ScoutLabel] = {
    Category.BL_COMPARISON: ScoutLabel.BILL_OF_LADING,
    Category.SI_REQUEST: ScoutLabel.SHIPPING_INSTRUCTION,
    Category.INVOICE_QUERY: ScoutLabel.INVOICE_OR_CHARGES,
    Category.GENERAL: ScoutLabel.OPERATIONAL_NOISE,
    Category.SPAM: ScoutLabel.OPERATIONAL_NOISE,
}

SCOUT_TO_CATEGORY: dict[ScoutLabel, Category] = {
    ScoutLabel.BOOKING_CONFIRMATION: Category.GENERAL,
    ScoutLabel.SHIPPING_INSTRUCTION: Category.SI_REQUEST,
    ScoutLabel.BILL_OF_LADING: Category.BL_COMPARISON,
    ScoutLabel.AMENDMENT_REQUEST: Category.GENERAL,
    ScoutLabel.DISCREPANCY_QUERY: Category.BL_COMPARISON,
    ScoutLabel.INVOICE_OR_CHARGES: Category.INVOICE_QUERY,
    ScoutLabel.OPERATIONAL_NOISE: Category.SPAM,
    ScoutLabel.UNKNOWN: Category.GENERAL,
}


class CourtState(str, Enum):
    """Per-field court outcome (deterministic). UNCERTAIN is Bridge-only."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNCERTAIN = "UNCERTAIN"


class CaseVerdict(str, Enum):
    """Roll-up card shown on the Bridge board."""

    CLEAR = "CLEAR"
    HOLD = "HOLD"
    PILOT = "PILOT"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FailureCode(str, Enum):
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_INVALID_JSON = "LLM_INVALID_JSON"
    ATTACHMENT_CORRUPT = "ATTACHMENT_CORRUPT"
    OCR_GARBLED = "OCR_GARBLED"
    EMPTY_EMAIL = "EMPTY_EMAIL"
    PARSER_MISS = "PARSER_MISS"
    DEGRADED_RULES_ONLY = "DEGRADED_RULES_ONLY"
    CHAOS_INJECTED = "CHAOS_INJECTED"


class PilotDecision(str, Enum):
    ACCEPT_AS_MATCH = "accept_as_match"
    CONFIRM_MISMATCH = "confirm_mismatch"
    DEFER = "defer"


# ── Evidence & fields ──────────────────────────────────────────────────


class BBox(BaseModel):
    page: int = 1
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0


class Evidence(BaseModel):
    raw_text: str = ""
    snippet: str = ""
    page: int | None = None
    bbox: BBox | None = None
    source: EvidenceSource = EvidenceSource.TEXT
    doc_id: str | None = None
    attachment_name: str | None = None


class FieldValue(BaseModel):
    name: str
    raw_value: str
    normalized: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence: Evidence = Field(default_factory=Evidence)

    @field_validator("confidence")
    @classmethod
    def _clamp_conf(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ExtractedDocument(BaseModel):
    doc_id: str = Field(default_factory=_new_id)
    filename: str = ""
    mime: str = ""
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    parser_used: str = ""
    degraded: bool = False
    text: str = ""
    kind: Literal["si", "bl", "other", "unknown"] = "unknown"
    page_count: int = 0


class AttachmentRef(BaseModel):
    path: str = ""
    filename: str = ""
    mime: str = ""
    local_path: str | None = None
    kind_hint: str | None = None


# ── Scout ──────────────────────────────────────────────────────────────


class ScoutResult(BaseModel):
    category: Category = Category.GENERAL
    label: ScoutLabel = ScoutLabel.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    route: Literal["rules", "llm", "unknown"] = "unknown"
    degraded: bool = False


# ── Court ──────────────────────────────────────────────────────────────


class Charge(BaseModel):
    """Prosecutor allegation: left vs right differ on a field."""

    field: str
    left: FieldValue
    right: FieldValue
    note: str = "raw inequality"


class Plea(BaseModel):
    strategy: str
    accepted: bool
    argument: str = ""
    transformed_left: str | None = None
    transformed_right: str | None = None
    confidence: float = 1.0


class FieldVerdict(BaseModel):
    field: str
    state: CourtState
    charge: Charge | None = None
    pleas: list[Plea] = Field(default_factory=list)
    winning_strategy: str | None = None
    rationale: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    exposure_usd: float = 0.0
    advise: str = ""


class TranscriptEvent(BaseModel):
    seq: int
    kind: Literal["charge", "plea", "verdict", "note"]
    field: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=_utcnow)


class CourtTranscript(BaseModel):
    case_id: str
    events: list[TranscriptEvent] = Field(default_factory=list)

    def add(
        self,
        kind: Literal["charge", "plea", "verdict", "note"],
        field: str,
        payload: dict[str, Any],
    ) -> TranscriptEvent:
        ev = TranscriptEvent(seq=len(self.events), kind=kind, field=field, payload=payload)
        self.events.append(ev)
        return ev


# ── Risk & report ──────────────────────────────────────────────────────


class RiskAdvice(BaseModel):
    field: str
    risk_level: RiskLevel
    exposure_usd: float
    advise: str
    weight: float = 0.5


class CaseCard(BaseModel):
    case_id: str = Field(default_factory=_new_id)
    email_id: str = ""
    subject: str = ""
    verdict: CaseVerdict = CaseVerdict.PILOT
    scout: ScoutResult | None = None
    field_verdicts: list[FieldVerdict] = Field(default_factory=list)
    total_exposure_usd: float = 0.0
    failure_codes: list[FailureCode] = Field(default_factory=list)
    degraded: bool = False
    reply_draft: str | None = None
    official: EmailVerdict | None = None
    ai_resolved: bool = False
    ai_pilot_note: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def mismatch_fields(self) -> list[str]:
        return [fv.field for fv in self.field_verdicts if fv.state == CourtState.MISMATCH]

    @property
    def uncertain_fields(self) -> list[str]:
        return [fv.field for fv in self.field_verdicts if fv.state == CourtState.UNCERTAIN]


# ── Ledger ─────────────────────────────────────────────────────────────


class LedgerRule(BaseModel):
    rule_id: str = Field(default_factory=_new_id)
    field: str
    left_pattern: str
    right_pattern: str
    normalized_key: str
    decision: PilotDecision
    source_case_id: str
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    created_by: str = "pilot"
    revoked_at: datetime | None = None
    note: str = ""


class PilotReview(BaseModel):
    review_id: str = Field(default_factory=_new_id)
    case_id: str
    field: str
    decision: PilotDecision
    promote_to_ledger: bool = True
    reviewer: str = "pilot"
    note: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ── Pipeline I/O ───────────────────────────────────────────────────────


class EmailMessage(BaseModel):
    email_id: str
    subject: str = ""
    body_text: str = ""
    from_addr: str = ""
    to_addrs: list[str] = Field(default_factory=list)
    received_at: datetime | None = None
    attachment_paths: list[str] = Field(default_factory=list)
    attachments: list[AttachmentRef] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    ok: bool = True
    reason: ReviewReason | None = None
    detail: str = ""
    si_filename: str | None = None
    bl_filename: str | None = None
    missing_fields: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    email_id: str | None = None
    dry_run: bool = False
    degrade: bool = False
    chaos: list[str] = Field(default_factory=list)
    full: bool = False
    rules_only: bool = False
    two_value: bool | None = None
    save_board: bool | None = None
    source: Literal["auto", "remote", "local", "official"] = "auto"


class RunResult(BaseModel):
    run_id: str = Field(default_factory=_new_id)
    card: CaseCard
    transcript: CourtTranscript | None = None
    submission: dict[str, Any] | None = None
    official: EmailVerdict | None = None
