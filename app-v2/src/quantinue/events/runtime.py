"""Minute-cadence runtime for incremental event sources."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol

import anyio

from quantinue.core.market_calendar import NEW_YORK
from quantinue.events.adapters import NewsEventSourceAdapter, SecEventSourceAdapter
from quantinue.events.evidence import EvidenceDocumentError
from quantinue.events.ingestion import (
    IncrementalEventSource,
    PostgresEventIngestionRepository,
    ingest_incrementally,
)
from quantinue.events.routing_repository import (
    PostgresEventRoutingRepository,
    route_pending_events,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from quantinue.events.evidence_repository import PostgresEventEvidenceRepository
    from quantinue.llm.provider import LlmAnalyzer
    from quantinue.orchestration.policy import EventIngestionConfig


class EventIngestor(Protocol):
    """Execute one configured source by name."""

    async def ingest(
        self, source_name: str, as_of: date
    ) -> EvidencePreparationRun | None:
        """Persist all currently available pages."""
        ...

    async def close(self) -> None:
        """Release resources owned by the ingestion boundary."""
        ...


@dataclass(frozen=True, slots=True)
class EvidencePreparationRun:
    """Truthful evidence outcomes from one source dispatch."""

    prepared: int
    failed: int


@dataclass
class EventIngestionExecutor:
    """Bind source adapters to the transactional repository."""

    config: EventIngestionConfig
    sources: Mapping[str, IncrementalEventSource]
    repository: PostgresEventIngestionRepository
    routing_repository: PostgresEventRoutingRepository
    evidence_repository: PostgresEventEvidenceRepository | None = None
    analyzer: LlmAnalyzer | None = None

    async def ingest(
        self, source_name: str, as_of: date
    ) -> EvidencePreparationRun | None:
        """Ingest one source, then route every durable pending event."""
        source = self.sources.get(source_name)
        if source is None:
            return None
        match source:
            case SecEventSourceAdapter() | NewsEventSourceAdapter():
                source = replace(source, now=datetime.now(UTC))
            case _:
                pass
        _ = await ingest_incrementally(
            source_name,
            source,
            self.repository,
            self.config.sources[source_name].overlap,
        )
        _ = await route_pending_events(self.routing_repository, as_of)
        if self.evidence_repository is None or self.analyzer is None:
            return None
        routes = await self.routing_repository.accepted_without_evidence()
        prepared = 0
        failed = 0
        for route in routes:
            try:
                _ = await self.evidence_repository.prepare(
                    route,
                    self.analyzer,
                    summary_timeout_seconds=self.config.summary_timeout_seconds,
                )
                prepared += 1
            except (EvidenceDocumentError, TimeoutError):
                failed += 1
        return EvidencePreparationRun(prepared=prepared, failed=failed)

    async def close(self) -> None:
        """Dispose both database pools even if the first close fails."""
        with anyio.CancelScope(shield=True):
            try:
                await self.repository.close()
            finally:
                try:
                    await self.routing_repository.close()
                finally:
                    if self.evidence_repository is not None:
                        await self.evidence_repository.close()


@dataclass
class EventIngestionRuntime:
    """Dispatch sources once at each elapsed cadence boundary."""

    config: EventIngestionConfig
    ingestor: EventIngestor
    _last_dispatch: dict[str, datetime] = field(default_factory=dict, init=False)
    last_evidence_run: EvidencePreparationRun | None = field(default=None, init=False)

    async def tick(self, now: datetime) -> None:
        """Dispatch due sources, coalescing delayed ticks into one run."""
        as_of = now.astimezone(NEW_YORK).date()
        evidence_runs: list[EvidencePreparationRun] = []
        for source_name, schedule in self.config.sources.items():
            previous = self._last_dispatch.get(source_name)
            if previous is not None and now - previous < schedule.cadence:
                continue
            result = await self.ingestor.ingest(source_name, as_of)
            if result is not None:
                evidence_runs.append(result)
            self._last_dispatch[source_name] = now
        if evidence_runs:
            self.last_evidence_run = EvidencePreparationRun(
                prepared=sum(run.prepared for run in evidence_runs),
                failed=sum(run.failed for run in evidence_runs),
            )
        else:
            self.last_evidence_run = None

    async def close(self) -> None:
        """Release resources owned by the executor."""
        with anyio.CancelScope(shield=True):
            await self.ingestor.close()
