from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from quantinue.events.runtime import EventIngestionRuntime
from quantinue.orchestration.policy import EventIngestionConfig


@dataclass
class Recorder:
    calls: list[str] = field(default_factory=list)

    async def ingest(self, source_name: str) -> None:
        self.calls.append(source_name)


@pytest.mark.anyio
async def test_compressed_clock_dispatches_exact_source_cadences() -> None:
    # Given
    recorder = Recorder()
    runtime = EventIngestionRuntime(EventIngestionConfig(), recorder)

    # When
    for minute in range(31):
        await runtime.tick(datetime(2026, 7, 24, 12, minute, tzinfo=UTC))

    # Then
    assert recorder.calls.count("sec") == 2
    assert recorder.calls.count("news") == 3
    assert recorder.calls.count("wire") == 4
