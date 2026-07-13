"""FastAPI request, response, and redacted control-room schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantinue.core.contracts import RunId, RunStatus, StageStatus
from quantinue.core.ontology import ModelProvider


class RunCreate(BaseModel):
    """Request to execute one pipeline cycle now."""

    model_config = ConfigDict(frozen=True)

    ticker: str = Field(default="NVDA", pattern=r"^[A-Z0-9.-]{1,12}$")

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        """Strip benign edge whitespace before enforcing the canonical alphabet."""
        return value.strip()


class HealthResponse(BaseModel):
    """Safe runtime mode summary."""

    model_config = ConfigDict(frozen=True)

    status: str
    broker_mode: str
    llm_mode: str


class AsyncRunStart(BaseModel):
    """Safe acknowledgement for an accepted asynchronous pipeline launch."""

    model_config = ConfigDict(frozen=True)

    accepted: bool
    ticker: str
    cycle_ts: datetime


class AttemptView(BaseModel):
    """One safe execution attempt without raw provider error content."""

    model_config = ConfigDict(frozen=True)

    attempt_no: int = Field(gt=0)
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None = Field(default=None, ge=0)
    failure_code: str | None = None


class StageView(BaseModel):
    """Stage state, timing, and durable-checkpoint summary."""

    model_config = ConfigDict(frozen=True)

    component: str
    name: str
    status: StageStatus
    summary: str
    attempts: tuple[AttemptView, ...]
    duration_ms: int | None = Field(default=None, ge=0)
    checkpointed: bool
    failure_code: str | None = None


class EvidenceView(BaseModel):
    """Source-addressable evidence and its parent lineage."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    component: str
    source: str
    source_ref: str
    observed_at: datetime
    captured_at: datetime
    confidence: float = Field(ge=0, le=1)
    parent_evidence_ids: tuple[str, ...]
    model_name: str | None = None
    model_provider: ModelProvider | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class OrderView(BaseModel):
    """Idempotency and reconciliation-safe order summary."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    client_order_id: str
    reconciliation_status: str
    quantity: int
    filled_avg_price: float


class ReviewView(BaseModel):
    """T+5 review summary linked to the pipeline run."""

    model_config = ConfigDict(frozen=True)

    outcome: str
    summary: str


class LiveStageView(BaseModel):
    """Canonical current or next stage for a running control-room projection."""

    model_config = ConfigDict(frozen=True)

    component: str
    name: str
    status: StageStatus


class SourceReferenceView(BaseModel):
    """Readable source reference with an optional validated browser destination."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(max_length=512)
    href: str | None = Field(default=None, max_length=512)


class CollectionDetailView(BaseModel):
    """Safe collection fact retained for the administrator detail panel."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(max_length=200)
    summary: str = Field(max_length=1_000)
    source: str = Field(max_length=120)
    reference: SourceReferenceView
    score: float | None = Field(default=None, ge=0, le=1)


class StrategyDetailView(BaseModel):
    """Safe strategist decision facts without model inputs or provider payloads."""

    model_config = ConfigDict(frozen=True)

    proposal: str = Field(max_length=64)
    rationale: str = Field(max_length=1_000)
    gate: str = Field(max_length=64)
    blockers: tuple[str, ...] = Field(max_length=12)
    conviction: float | None = Field(default=None, ge=0, le=1)


class CriticDetailView(BaseModel):
    """Safe critic verdict facts without raw exception or provider detail."""

    model_config = ConfigDict(frozen=True)

    verdict: str = Field(max_length=64)
    rationale: str = Field(max_length=1_000)
    layer: str = Field(max_length=64)


class TerminalRunDetailView(BaseModel):
    """Redacted collection-to-critic detail for one terminal pipeline run."""

    model_config = ConfigDict(frozen=True)

    disclosure: CollectionDetailView
    news: CollectionDetailView
    strategy: StrategyDetailView
    critic: CriticDetailView


class ControlRoomRun(BaseModel):
    """Complete redacted observability projection used by API and HTML."""

    model_config = ConfigDict(frozen=True)

    run_id: RunId
    ticker: str
    cycle_ts: datetime
    status: RunStatus
    progress: int = Field(ge=0, le=11)
    current_stage: LiveStageView | None
    next_stage: LiveStageView | None
    stages: tuple[StageView, ...]
    evidence: tuple[EvidenceView, ...]
    conviction: float | None
    side: str | None
    detail: TerminalRunDetailView
    order: OrderView | None
    review: ReviewView | None
