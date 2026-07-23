"""Minute-cadence runtime for incremental event sources."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from quantinue.events.adapters import NewsEventSourceAdapter, SecEventSourceAdapter
from quantinue.events.ingestion import (
    IncrementalEventSource,
    PostgresEventIngestionRepository,
    ingest_incrementally,
)
from quantinue.orchestration.policy import EventIngestionConfig


class EventIngestor(Protocol):
    """Execute one configured source by name."""

    async def ingest(self, source_name: str) -> None:
        """Persist all currently available pages."""
        ...


@dataclass
class EventIngestionExecutor:
    """Bind source adapters to the transactional repository."""

    config: EventIngestionConfig
    sources: dict[str, IncrementalEventSource]
    repository: PostgresEventIngestionRepository

    async def ingest(self, source_name: str) -> None:
        """Run one source with its configured overlap."""
        source = self.sources.get(source_name)
        if source is None:
            return
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


@dataclass
class EventIngestionRuntime:
    """Dispatch sources once at each elapsed cadence boundary."""

    config: EventIngestionConfig
    ingestor: EventIngestor
    _last_dispatch: dict[str, datetime] = field(default_factory=dict, init=False)

    async def tick(self, now: datetime) -> None:
        """Dispatch due sources, coalescing delayed ticks into one run."""
        for source_name, schedule in self.config.sources.items():
            previous = self._last_dispatch.get(source_name)
            if previous is not None and now - previous < schedule.cadence:
                continue
            await self.ingestor.ingest(source_name)
            self._last_dispatch[source_name] = now
