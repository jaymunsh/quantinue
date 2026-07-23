from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from typing_extensions import override

from quantinue.orchestration.policy import WatchConfig
from quantinue.orchestration.watch_runner import WatchOutcome, WatchRunner
from quantinue.runtime_status import RuntimeSnapshot, present_runtime


class _FailingRunner(WatchRunner):
    @override
    async def _tick(self, now: datetime) -> WatchOutcome:
        assert now.tzinfo is not None
        raise TimeoutError


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
