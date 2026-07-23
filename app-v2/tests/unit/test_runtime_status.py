from datetime import UTC, datetime, timedelta

import anyio
import pytest
from pydantic import ValidationError
from typing_extensions import override

from quantinue.orchestration.policy import WatchConfig
from quantinue.orchestration.watch_runner import WatchOutcome, WatchRunner
from quantinue.runtime_status import EventSourceSnapshot, RuntimeSnapshot, present_runtime


class _FailingRunner(WatchRunner):
    @override
    async def _tick(self, now: datetime) -> WatchOutcome:
        assert now.tzinfo is not None
        raise TimeoutError


class _CancelThenReadyRunner(WatchRunner):
    def __init__(self, entered: anyio.Event) -> None:
        super().__init__(WatchConfig(enabled=True))
        self.entered = entered
        self.attempts = 0

    @override
    async def _tick(self, now: datetime) -> WatchOutcome:
        assert now.tzinfo is not None
        self.attempts += 1
        if self.attempts == 1:
            self.entered.set()
            await anyio.sleep_forever()
        return WatchOutcome("ready")


@pytest.mark.anyio
async def test_normal_cancellation_is_not_recorded_as_failure_and_next_tick_resumes() -> None:
    entered = anyio.Event()
    runner = _CancelThenReadyRunner(entered)
    cancelled_at = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)

    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(runner.tick, cancelled_at)
        await entered.wait()
        task_group.cancel_scope.cancel()

    cancelled = runner.snapshot()
    assert cancelled.last_poll_attempt is None
    assert cancelled.last_ready_poll is None
    assert cancelled.last_outcome == "never"
    assert cancelled.consecutive_failures == 0

    resumed_at = cancelled_at + timedelta(minutes=1)
    outcome = await runner.tick(resumed_at)
    resumed = runner.snapshot()
    assert outcome.reason == "ready"
    assert resumed.last_poll_attempt == resumed_at
    assert resumed.last_ready_poll == resumed_at
    assert resumed.last_outcome == "ready"
    assert resumed.consecutive_failures == 0


@pytest.mark.anyio
async def test_snapshot_records_ready_and_failed_tick_boundaries() -> None:
    runner = WatchRunner(WatchConfig(enabled=True))
    ready_at = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)

    _ = await runner.tick(ready_at)
    ready = runner.snapshot()

    assert ready.last_poll_attempt == ready_at
    assert ready.last_ready_poll == ready_at
    assert ready.last_outcome == "ready"
    assert ready.consecutive_failures == 0


def test_regular_session_stale_ready_poll_needs_attention() -> None:
    now = datetime(2026, 7, 20, 14, 4, tzinfo=UTC)
    snapshot = RuntimeSnapshot(
        background_workers=True,
        daily_attached=True,
        watch_attached=True,
        rejudge_configured=True,
        stream_configured=False,
        stream_state="off",
        last_poll_attempt=now - timedelta(minutes=1),
        last_ready_poll=now - timedelta(minutes=4),
        last_outcome="ready",
        consecutive_failures=0,
    )

    view = present_runtime(snapshot, now=now)

    assert view.watch_status == "attention"


def test_outside_session_is_closed_not_failed() -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    snapshot = RuntimeSnapshot.owner(
        daily_attached=True,
        watch_attached=True,
        rejudge_configured=False,
        stream_configured=False,
    )

    view = present_runtime(snapshot, now=now)

    assert view.watch_status == "closed"


def test_owner_reports_configured_attached_and_stream_reconnecting() -> None:
    snapshot = RuntimeSnapshot.owner(
        daily_attached=True,
        watch_attached=True,
        rejudge_configured=True,
        stream_configured=True,
        stream_state="reconnecting",
    )

    assert snapshot.background_workers is True
    assert snapshot.daily_attached is True
    assert snapshot.watch_attached is True
    assert snapshot.rejudge_configured is True
    assert snapshot.stream_configured is True
    assert snapshot.stream_state == "reconnecting"


def test_web_only_snapshot_reports_workers_off_despite_configured_policy() -> None:
    snapshot = RuntimeSnapshot.web_only(
        rejudge_configured=True,
        stream_configured=True,
    )

    assert snapshot.background_workers is False
    assert snapshot.daily_attached is False
    assert snapshot.watch_attached is False
    assert snapshot.rejudge_configured is True
    assert snapshot.stream_configured is True


def test_runtime_snapshot_rejects_missing_or_invalid_machine_state() -> None:
    with pytest.raises(ValidationError):
        RuntimeSnapshot.model_validate(
            {
                "background_workers": True,
                "daily_attached": True,
                "watch_attached": True,
                "rejudge_configured": True,
                "stream_configured": True,
                "stream_state": "unknown",
                "consecutive_failures": -1,
            }
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            EventSourceSnapshot(source_name="sec", cadence_seconds=1800),
            "stopped",
        ),
        (
            EventSourceSnapshot(
                source_name="news",
                cadence_seconds=900,
                last_attempt=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
                last_success=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
            ),
            "idle",
        ),
        (
            EventSourceSnapshot(
                source_name="wire",
                cadence_seconds=600,
                last_attempt=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
                last_success=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
                new_count=3,
            ),
            "active",
        ),
        (
            EventSourceSnapshot(
                source_name="sec",
                cadence_seconds=1800,
                last_attempt=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
                failed_count=1,
            ),
            "degraded",
        ),
        (
            EventSourceSnapshot(
                source_name="news",
                cadence_seconds=900,
                last_attempt=datetime(2026, 7, 20, 13, 0, tzinfo=UTC),
                last_success=datetime(2026, 7, 20, 13, 0, tzinfo=UTC),
            ),
            "stale",
        ),
    ],
)
def test_event_source_status_distinguishes_operator_outcomes(
    source: EventSourceSnapshot,
    expected: str,
) -> None:
    now = datetime(2026, 7, 20, 14, 1, tzinfo=UTC)
    snapshot = RuntimeSnapshot.web_only(
        rejudge_configured=False,
        stream_configured=False,
    ).model_copy(update={"event_sources": (source,)})

    view = present_runtime(snapshot, now=now)

    assert view.event_sources[0].status == expected


@pytest.mark.anyio
async def test_repeated_tick_failures_increment_without_disabling_runner() -> None:
    runner = _FailingRunner(WatchConfig(enabled=True))
    now = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)

    for offset in range(2):
        with pytest.raises(TimeoutError):
            _ = await runner.tick(now + timedelta(minutes=offset))

    snapshot = runner.snapshot()
    assert snapshot.last_outcome == "failed"
    assert snapshot.consecutive_failures == 2
