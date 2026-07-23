"""Process-local worker ownership and intraday liveness state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from quantinue.core.market_calendar import NyseCalendar

StreamState = Literal["off", "connecting", "connected", "reconnecting", "failed"]
PollOutcome = Literal["never", "disabled", "market_closed", "ready", "failed"]
WatchStatus = Literal["off", "waiting", "ready", "attention", "closed"]
EventSourceStatus = Literal["stopped", "idle", "active", "degraded", "stale"]


class EventSourceSnapshot(BaseModel):
    """Secret-free liveness counters for one incremental event source."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    cadence_seconds: int = Field(ge=1)
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    new_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)


class EventSourceView(BaseModel):
    """Operator classification for one incremental source."""

    model_config = ConfigDict(frozen=True)

    snapshot: EventSourceSnapshot
    status: EventSourceStatus


class RuntimeSnapshot(BaseModel):
    """Immutable process-local state that is never persisted per poll."""

    model_config = ConfigDict(frozen=True)

    background_workers: bool
    daily_attached: bool
    watch_attached: bool
    rejudge_configured: bool
    stream_configured: bool
    stream_state: StreamState = "off"
    last_poll_attempt: datetime | None = None
    last_ready_poll: datetime | None = None
    last_outcome: PollOutcome = "never"
    consecutive_failures: int = Field(default=0, ge=0)
    event_sources: tuple[EventSourceSnapshot, ...] = ()

    @classmethod
    def web_only(cls, *, rejudge_configured: bool, stream_configured: bool) -> RuntimeSnapshot:
        """Create a configured-but-unattached web process snapshot."""
        return cls(
            background_workers=False,
            daily_attached=False,
            watch_attached=False,
            rejudge_configured=rejudge_configured,
            stream_configured=stream_configured,
        )

    @classmethod
    def owner(
        cls,
        *,
        daily_attached: bool,
        watch_attached: bool,
        rejudge_configured: bool,
        stream_configured: bool,
        stream_state: StreamState = "off",
    ) -> RuntimeSnapshot:
        """Create a background-worker owner snapshot."""
        return cls(
            background_workers=True,
            daily_attached=daily_attached,
            watch_attached=watch_attached,
            rejudge_configured=rejudge_configured,
            stream_configured=stream_configured,
            stream_state=stream_state,
        )


class RuntimeView(BaseModel):
    """Operator-facing status derived from a runtime snapshot."""

    model_config = ConfigDict(frozen=True)

    snapshot: RuntimeSnapshot
    watch_status: WatchStatus
    event_sources: tuple[EventSourceView, ...] = ()


class WatchRuntimeState:
    """Mutable accumulator owned by one watch runner."""

    __slots__ = (
        "_consecutive_failures",
        "_last_outcome",
        "_last_poll_attempt",
        "_last_ready_poll",
        "_rejudge_configured",
        "_stream_configured",
    )

    def __init__(self, *, rejudge_configured: bool, stream_configured: bool) -> None:
        """Initialize empty liveness for one attached runner."""
        self._rejudge_configured = rejudge_configured
        self._stream_configured = stream_configured
        self._last_poll_attempt: datetime | None = None
        self._last_ready_poll: datetime | None = None
        self._last_outcome: PollOutcome = "never"
        self._consecutive_failures = 0

    def snapshot(self, *, stream_state: StreamState) -> RuntimeSnapshot:
        """Copy accumulated state into the read-only boundary type."""
        return RuntimeSnapshot(
            background_workers=True,
            daily_attached=False,
            watch_attached=True,
            rejudge_configured=self._rejudge_configured,
            stream_configured=self._stream_configured,
            stream_state=stream_state,
            last_poll_attempt=self._last_poll_attempt,
            last_ready_poll=self._last_ready_poll,
            last_outcome=self._last_outcome,
            consecutive_failures=self._consecutive_failures,
        )

    def record(self, attempted_at: datetime, outcome: PollOutcome) -> None:
        """Record one completed or failed polling boundary."""
        self._last_poll_attempt = attempted_at
        self._last_outcome = outcome
        if outcome == "failed":
            self._consecutive_failures += 1
            return
        self._consecutive_failures = 0
        if outcome == "ready":
            self._last_ready_poll = attempted_at


def present_runtime(
    snapshot: RuntimeSnapshot, *, now: datetime, calendar: NyseCalendar | None = None
) -> RuntimeView:
    """Classify polling health against the current market session."""
    market = calendar or NyseCalendar()
    if not snapshot.background_workers or not snapshot.watch_attached:
        status: WatchStatus = "off"
    elif not market.is_market_open(now):
        status = "closed"
    elif snapshot.consecutive_failures > 0:
        status = "attention"
    elif snapshot.last_ready_poll is None:
        status = "waiting"
    elif now - snapshot.last_ready_poll > timedelta(minutes=3):
        status = "attention"
    else:
        status = "ready"
    return RuntimeView(
        snapshot=snapshot,
        watch_status=status,
        event_sources=tuple(
            EventSourceView(
                snapshot=source,
                status=present_event_source(source, now=now),
            )
            for source in snapshot.event_sources
        ),
    )


def present_event_source(snapshot: EventSourceSnapshot, *, now: datetime) -> EventSourceStatus:
    """Distinguish stopped, failed, quiet, active, and stale collection."""
    if snapshot.last_attempt is None:
        return "stopped"
    if snapshot.failed_count > 0 and (
        snapshot.last_success is None or snapshot.last_attempt > snapshot.last_success
    ):
        return "degraded"
    if snapshot.last_success is None:
        return "degraded"
    if now - snapshot.last_success > timedelta(seconds=snapshot.cadence_seconds * 2):
        return "stale"
    return "active" if snapshot.new_count > 0 else "idle"
