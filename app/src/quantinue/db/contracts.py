"""Persistence contracts for claimed runs and atomic stage boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import date, datetime

    from quantinue.core.contracts import PipelineContext, PipelineRequest, PipelineRun, RunId
    from quantinue.db.active_snapshot import ActivePipelineSnapshot


@dataclass(frozen=True, slots=True)
class PersistedAttempt:
    """Observable execution attempt for one canonical component."""

    component: str
    attempt_no: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class AttemptFailure:
    """Redacted stable failure persisted for one attempt."""

    status: str
    error_code: str
    error_message: str


@dataclass(frozen=True, slots=True)
class RunClaim:
    """Atomic claim outcome with the last durable context, when acquired."""

    acquired: bool
    terminal_run: PipelineRun | None = None
    context: PipelineContext | None = None


@dataclass(frozen=True, slots=True)
class DailyOrderReservation:
    """Complete canonical planned order used by the atomic daily cap gate."""

    account_id: int
    trade_date: date
    signal_id: int
    idempotency_key: str
    ticker: str
    quantity: int
    entry_price: float
    stop_price: float
    take_profit_price: float
    cap: int


class RunStore(Protocol):
    """Persistence boundary used by orchestration and operational views."""

    async def initialize(self) -> None:
        """Prepare storage."""
        ...

    async def close(self) -> None:
        """Release storage resources."""
        ...

    async def claim(
        self, key: str, request: PipelineRequest, *, resume_failed: bool = False
    ) -> RunClaim:
        """Atomically claim a run key."""
        ...

    async def wait_for_release(self, key: str) -> PipelineRun | None:
        """Wait for the current claimant."""
        ...

    async def complete_stage(
        self,
        key: str,
        context: PipelineContext,
        attempt: PersistedAttempt,
    ) -> None:
        """Commit an attempt and checkpoint atomically."""
        ...

    async def start_attempt(
        self,
        key: str,
        component: str,
        started_at: datetime,
    ) -> PersistedAttempt:
        """Persist a running attempt."""
        ...

    async def fail_attempt(
        self,
        key: str,
        attempt: PersistedAttempt,
        finished_at: datetime,
        failure: AttemptFailure,
    ) -> None:
        """Persist a failed attempt."""
        ...

    async def finish_run(self, key: str, run: PipelineRun, *, resumable: bool = False) -> None:
        """Publish a terminal run."""
        ...

    async def abandon(self, key: str) -> None:
        """Release a nonterminal claim."""
        ...

    async def get_by_key(self, key: str) -> PipelineRun | None:
        """Get a terminal run by key."""
        ...

    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        """List attempts in insertion order."""
        ...

    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        """List recent terminal runs."""
        ...

    async def list_active(self, limit: int = 20) -> tuple[ActivePipelineSnapshot, ...]:
        """List safe snapshots for nonterminal runs only."""
        ...

    async def reserve_daily_new_order(self, request: DailyOrderReservation) -> bool:
        """Atomically reserve one canonical order unless the account/day cap is full."""
        ...
