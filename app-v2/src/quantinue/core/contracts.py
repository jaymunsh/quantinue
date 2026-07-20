"""Source records shared by collection adapters and the domain ledger.

Phase 5까지는 11단계 런의 계약(PipelineRun·PipelineContext·Stage*)이 살던
모듈이다. 그 절반은 구 러너와 함께 죽었다 — 남은 것은 공시·뉴스 원본
레코드뿐이고, 이 둘은 수집 어댑터와 도메인 원장이 공유하는 계약이라
러너와 무관하게 산다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - 런타임 dataclass 필드 타입

from quantinue.core.ontology import ModelProvider
from quantinue.market_data.models import NewsMatchReason, NewsMatchStatus


@dataclass(frozen=True, slots=True)
class DisclosureSourceRecord:
    """Minimal SEC filing actually consumed by role 05."""

    filing_no: str
    title: str
    form_type: str
    filed_at: datetime
    event_type: str
    source_ref: str
    summary: str
    source: str = "sec-edgar"
    captured_at: datetime | None = None
    confidence: float = 1.0
    evidence_id: str = ""
    parent_evidence_ids: tuple[str, ...] = ()
    model_provider: ModelProvider = ModelProvider.MOCK
    model_name: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    input_hash: str | None = None


@dataclass(frozen=True, slots=True)
class NewsSourceRecord:
    """Minimal RSS item actually consumed by role 06."""

    news_key: str
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str
    captured_at: datetime | None = None
    confidence: float = 1.0
    evidence_id: str = ""
    parent_evidence_ids: tuple[str, ...] = ()
    model_provider: ModelProvider = ModelProvider.MOCK
    model_name: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    input_hash: str | None = None
    selection_status: NewsMatchStatus = NewsMatchStatus.FETCHED
    relevance_score: int = 0
    relevance_reasons: tuple[NewsMatchReason, ...] = ()
    canonical_identity: str = ""
