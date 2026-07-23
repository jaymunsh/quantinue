from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from quantinue.events.runtime import EventIngestionRuntime
from quantinue.orchestration.policy import EventIngestionConfig


@dataclass
class Recorder:
    calls: list[tuple[str, date]] = field(default_factory=list)
    closed: bool = False

    async def ingest(self, source_name: str, as_of: date) -> None:
        self.calls.append((source_name, as_of))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_compressed_clock_dispatches_exact_source_cadences() -> None:
    # Given
    recorder = Recorder()
    runtime = EventIngestionRuntime(EventIngestionConfig(), recorder)

    # When
    for minute in range(31):
        await runtime.tick(datetime(2026, 7, 24, 12, minute, tzinfo=UTC))

    # Then
    assert [source for source, _ in recorder.calls].count("sec") == 2
    assert [source for source, _ in recorder.calls].count("news") == 3
    assert [source for source, _ in recorder.calls].count("wire") == 4
    assert {as_of for _, as_of in recorder.calls} == {date(2026, 7, 24)}


@pytest.mark.anyio
async def test_runtime_closes_the_ingestion_and_routing_owner() -> None:
    # Given
    recorder = Recorder()
    runtime = EventIngestionRuntime(EventIngestionConfig(), recorder)

    # When
    await runtime.close()

    # Then
    assert recorder.closed
