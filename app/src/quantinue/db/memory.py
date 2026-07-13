"""Behavioral in-memory fake for the durable run repository."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import anyio

from quantinue.core.contracts import PipelineContext, PipelineRequest, PipelineRun, RunId
from quantinue.db.active_snapshot import ActivePipelineSnapshot, active_pipeline_snapshot
from quantinue.db.contracts import (
    AttemptFailure,
    DailyOrderReservation,
    PersistedAttempt,
    RunClaim,
)


class InMemoryRunStore:
    """Mutable process-local fake with atomic claim and checkpoint semantics."""

    def __init__(self) -> None:
        """Create empty atomic fake state."""
        self._runs: dict[str, PipelineRun] = {}
        self._contexts: dict[str, PipelineContext] = {}
        self._attempts: dict[str, list[PersistedAttempt]] = {}
        self._active: dict[str, anyio.Event] = {}
        self._resumable: set[str] = set()
        self._lock = anyio.Lock()
        self._daily_orders: dict[tuple[int, date], set[str]] = {}

    async def initialize(self) -> None:
        """No initialization is required."""

    async def close(self) -> None:
        """No external resources are owned."""

    async def claim(
        self, key: str, request: PipelineRequest, *, resume_failed: bool = False
    ) -> RunClaim:
        """Claim a key once or expose its completed outcome."""
        async with self._lock:
            terminal = self._runs.get(key)
            if terminal is not None and not (resume_failed and key in self._resumable):
                return RunClaim(acquired=False, terminal_run=terminal)
            if key in self._active:
                return RunClaim(acquired=False)
            self._active[key] = anyio.Event()
            _ = self._runs.pop(key, None)
            context = self._contexts.get(key, PipelineContext(request=request))
            self._contexts[key] = context
            attempts = self._attempts.setdefault(key, [])
            now = datetime.now().astimezone()
            self._attempts[key] = [
                replace(
                    item,
                    status="failed",
                    finished_at=now,
                    error_code="ABANDONED_ATTEMPT",
                    error_message="prior owner exited before attempt finalization",
                )
                if item.status == "running"
                else item
                for item in attempts
            ]
            return RunClaim(acquired=True, context=context)

    async def wait_for_release(self, key: str) -> PipelineRun | None:
        """Wait until the current owner completes or abandons its claim."""
        async with self._lock:
            event = self._active.get(key)
            terminal = self._runs.get(key)
        if event is not None:
            await event.wait()
        return self._runs.get(key, terminal)

    async def start_attempt(
        self, key: str, component: str, started_at: datetime
    ) -> PersistedAttempt:
        """Append the next one-based attempt for a component."""
        attempts = self._attempts[key]
        number = 1 + sum(item.component == component for item in attempts)
        attempt = PersistedAttempt(component, number, "running", started_at)
        attempts.append(attempt)
        return attempt

    async def complete_stage(
        self, key: str, context: PipelineContext, attempt: PersistedAttempt
    ) -> None:
        """Atomically persist a completed attempt and its resulting context."""
        finished = replace(attempt, status="completed", finished_at=datetime.now().astimezone())
        attempts = self._attempts[key]
        attempts[attempts.index(attempt)] = finished
        self._contexts[key] = context

    async def fail_attempt(
        self,
        key: str,
        attempt: PersistedAttempt,
        finished_at: datetime,
        failure: AttemptFailure,
    ) -> None:
        """Persist a typed failure observation."""
        failed = replace(
            attempt,
            status=failure.status,
            finished_at=finished_at,
            error_code=failure.error_code,
            error_message=failure.error_message,
        )
        attempts = self._attempts[key]
        attempts[attempts.index(attempt)] = failed

    async def finish_run(self, key: str, run: PipelineRun, *, resumable: bool = False) -> None:
        """Publish the terminal snapshot and release waiters."""
        async with self._lock:
            self._runs[key] = run
            if resumable:
                self._resumable.add(key)
            else:
                self._resumable.discard(key)
            event = self._active.pop(key)
            event.set()

    async def abandon(self, key: str) -> None:
        """Release an interrupted claim while preserving its checkpoint."""
        async with self._lock:
            event = self._active.pop(key, None)
            if event is not None:
                event.set()

    async def get_by_key(self, key: str) -> PipelineRun | None:
        """Return a terminal run by key."""
        return self._runs.get(key)

    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        """Return attempts for a run in insertion order."""
        for key, context in self._contexts.items():
            if context.run_id == run_id:
                return tuple(self._attempts[key])
        return ()

    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        """Return recent terminal runs."""
        return tuple(
            sorted(self._runs.values(), key=lambda run: run.cycle_ts, reverse=True)[:limit]
        )

    async def list_active(self, limit: int = 20) -> tuple[ActivePipelineSnapshot, ...]:
        """Return current claimed contexts with redacted attempt detail."""
        async with self._lock:
            active_contexts = tuple(
                (context, tuple(self._attempts[key]))
                for key, context in self._contexts.items()
                if key in self._active
            )
        ordered = sorted(active_contexts, key=lambda item: item[0].request.cycle_ts, reverse=True)
        return tuple(
            active_pipeline_snapshot(context, attempts) for context, attempts in ordered[:limit]
        )

    async def reserve_daily_new_order(self, request: DailyOrderReservation) -> bool:
        """Atomically reserve a stable order identity within an account/day cap."""
        async with self._lock:
            identities = self._daily_orders.setdefault(
                (request.account_id, request.trade_date), set()
            )
            if request.idempotency_key in identities:
                return True
            if len(identities) >= request.cap:
                return False
            identities.add(request.idempotency_key)
            return True
