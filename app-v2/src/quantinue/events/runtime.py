"""Minute-cadence runtime for incremental event sources."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Protocol

from quantinue.core.market_calendar import NEW_YORK
from quantinue.events.adapters import NewsEventSourceAdapter, SecEventSourceAdapter
from quantinue.events.ingestion import (
    IncrementalEventSource,
    PostgresEventIngestionRepository,
    ingest_incrementally,
)
from quantinue.events.routing_repository import (
    PostgresEventRoutingRepository,
    route_pending_events,
)
from quantinue.orchestration.policy import EventIngestionConfig


class EventIngestor(Protocol):
    """Execute one configured source by name."""

    async def ingest(self, source_name: str, as_of: date) -> None:
        """Persist all currently available pages."""
        ...

    async def close(self) -> None:
        """Release resources owned by the ingestion boundary."""
        ...


@dataclass
class EventIngestionExecutor:
    """Bind source adapters to the transactional repository."""

    config: EventIngestionConfig
    sources: Mapping[str, IncrementalEventSource]
    repository: PostgresEventIngestionRepository
    routing_repository: PostgresEventRoutingRepository

    async def ingest(self, source_name: str, as_of: date) -> None:
        """Ingest one source, then route every durable pending event."""
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
        _ = await route_pending_events(self.routing_repository, as_of)

    async def close(self) -> None:
        """Dispose both database pools even if the first close fails."""
        try:
            await self.repository.close()
        finally:
            await self.routing_repository.close()


@dataclass
class EventIngestionRuntime:
    """Dispatch sources once at each elapsed cadence boundary."""

    config: EventIngestionConfig
    ingestor: EventIngestor
    _last_dispatch: dict[str, datetime] = field(default_factory=dict, init=False)

    async def tick(self, now: datetime) -> None:
        """Dispatch due sources, coalescing delayed ticks into one run."""
        as_of = now.astimezone(NEW_YORK).date()
        for source_name, schedule in self.config.sources.items():
            previous = self._last_dispatch.get(source_name)
            if previous is not None and now - previous < schedule.cadence:
                continue
            await self.ingestor.ingest(source_name, as_of)
            self._last_dispatch[source_name] = now

    async def close(self) -> None:
        """Release resources owned by the executor."""
        await self.ingestor.close()
