from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from quantinue.orchestration.job_runner import JobRunner
from quantinue.orchestration.policy import JobsConfig


@dataclass
class Ledger:
    async def reserve_job_run(self, job_name: str, slot_date: date) -> bool:
        _ = job_name, slot_date
        return True

    async def finish_job_run(
        self,
        job_name: str,
        slot_date: date,
        *,
        succeeded: bool,
        detail: str | None = None,
    ) -> None:
        _ = job_name, slot_date, succeeded, detail

    async def last_job_success(self, job_name: str) -> date | None:
        _ = job_name
        return None


@dataclass
class EventRuntime:
    calls: list[datetime] = field(default_factory=list)

    async def tick(self, now: datetime) -> None:
        self.calls.append(now)


@pytest.mark.anyio
async def test_production_runner_dispatches_only_in_premarket_or_regular_session() -> None:
    # Given
    events = EventRuntime()
    runner = JobRunner(
        JobsConfig(enabled=True),
        Ledger(),
        (),
        event_runtime=events,
    )

    # When
    for moment in (
        datetime(2026, 7, 25, 14, tzinfo=UTC),
        datetime(2026, 1, 1, 14, tzinfo=UTC),
        datetime(2026, 7, 24, 6, tzinfo=UTC),
        datetime(2026, 7, 24, 8, tzinfo=UTC),
        datetime(2026, 7, 24, 14, tzinfo=UTC),
    ):
        _ = await runner.tick(moment)

    # Then
    assert events.calls == [
        datetime(2026, 7, 24, 8, tzinfo=UTC),
        datetime(2026, 7, 24, 14, tzinfo=UTC),
    ]
