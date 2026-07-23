from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, cast

import anyio
import pytest
from typing_extensions import override

from quantinue.events.runtime import (
    EventIngestionExecutor,
    EventIngestionRuntime,
    EvidencePreparationRun,
)
from quantinue.orchestration.policy import EventIngestionConfig

if TYPE_CHECKING:
    from quantinue.events.evidence_repository import PostgresEventEvidenceRepository
    from quantinue.events.ingestion import PostgresEventIngestionRepository
    from quantinue.events.routing_repository import PostgresEventRoutingRepository


@dataclass
class Recorder:
    calls: list[tuple[str, date]] = field(default_factory=list)
    closed: bool = False

    async def ingest(self, source_name: str, as_of: date) -> None:
        self.calls.append((source_name, as_of))

    async def prepare_evidence(self, now: datetime) -> EvidencePreparationRun | None:
        _ = now
        return None

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


@pytest.mark.anyio
async def test_runtime_close_finishes_awaited_disposal_under_cancellation() -> None:
    class AwaitingRecorder(Recorder):
        started = anyio.Event()
        release = anyio.Event()

        @override
        async def close(self) -> None:
            self.started.set()
            await self.release.wait()
            self.closed = True

    recorder = AwaitingRecorder()
    runtime = EventIngestionRuntime(EventIngestionConfig(), recorder)

    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(runtime.close)
        await recorder.started.wait()
        task_group.cancel_scope.cancel()
        recorder.release.set()

    assert recorder.closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "first_errors",
    [(RuntimeError("runtime"), ValueError("value"), OSError("os"))],
)
async def test_executor_close_attempts_all_three_pools_once_and_raises_first_error(
    first_errors: tuple[Exception, ...],
) -> None:
    class CloseRecorder:
        def __init__(self, name: str, calls: list[str], error: Exception | None) -> None:
            self.name = name
            self.calls = calls
            self.error = error

        async def close(self) -> None:
            self.calls.append(self.name)
            if self.error is not None:
                raise self.error

    for first_error in first_errors:
        calls: list[str] = []
        executor = EventIngestionExecutor(
            config=EventIngestionConfig(),
            sources={},
            repository=cast(
                "PostgresEventIngestionRepository",
                cast("object", CloseRecorder("ingestion", calls, first_error)),
            ),
            routing_repository=cast(
                "PostgresEventRoutingRepository",
                cast("object", CloseRecorder("routing", calls, ValueError("routing failed"))),
            ),
            evidence_repository=cast(
                "PostgresEventEvidenceRepository",
                cast("object", CloseRecorder("evidence", calls, OSError("evidence failed"))),
            ),
        )

        with pytest.raises((RuntimeError, ValueError, OSError)) as caught:
            await executor.close()

        assert caught.value is first_error
        assert calls == ["ingestion", "routing", "evidence"]


@pytest.mark.anyio
async def test_sec_news_wire_share_one_poison_evidence_attempt() -> None:
    class CountingRecorder(Recorder):
        poison_attempts = 0

        @override
        async def prepare_evidence(self, now: datetime) -> EvidencePreparationRun:
            _ = now
            self.poison_attempts += 1
            return EvidencePreparationRun(prepared=0, failed=1)

    recorder = CountingRecorder()
    runtime = EventIngestionRuntime(EventIngestionConfig(), recorder)

    await runtime.tick(datetime(2026, 7, 24, 12, tzinfo=UTC))

    assert [source for source, _ in recorder.calls] == ["sec", "news", "wire"]
    assert recorder.poison_attempts == 1
    assert runtime.last_evidence_run == EvidencePreparationRun(prepared=0, failed=1)
