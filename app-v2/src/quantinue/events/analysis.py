"""Stage-granular dispatch contracts for routed event rejudgements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import anyio

if TYPE_CHECKING:
    from datetime import datetime, timedelta
    from decimal import Decimal

    from pydantic import JsonValue

    from quantinue.events.analysis_repository import (
        EventAnalysisReceiptClaim,
        EventAnalysisStage,
    )
    from quantinue.events.evidence import EvidencePack
    from quantinue.llm.budget import LlmBudgetReservation


@dataclass(frozen=True, slots=True)
class EventDecision:
    """One event judgement eligible for the existing order paths."""

    ticker: str
    persona: str
    side: str
    reference_price: Decimal
    approved: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class EventAnalysisRun:
    """Truthful stage outcomes from one accepted event fan-out."""

    attempted: int = 0
    completed: int = 0
    reused: int = 0
    suppressed: int = 0
    failed: int = 0
    uncertain: int = 0
    reason: str = "no_analysis"
    decisions: tuple[EventDecision, ...] = ()

    def __add__(self, other: EventAnalysisRun) -> EventAnalysisRun:
        """Combine counters while retaining every non-empty reason."""
        reasons = tuple(reason for reason in (self.reason, other.reason) if reason != "no_analysis")
        return EventAnalysisRun(
            attempted=self.attempted + other.attempted,
            completed=self.completed + other.completed,
            reused=self.reused + other.reused,
            suppressed=self.suppressed + other.suppressed,
            failed=self.failed + other.failed,
            uncertain=self.uncertain + other.uncertain,
            reason=",".join(reasons) if reasons else "no_analysis",
            decisions=self.decisions + other.decisions,
        )


class EventAnalysisReceiptRepository(Protocol):
    """Durable stage operations used at paid provider boundaries."""

    async def claim(  # noqa: PLR0913 - durable key, policy, and owner are independent
        self,
        pack: EvidencePack,
        persona: str,
        stage: EventAnalysisStage,
        now: datetime,
        cooldown: timedelta,
        owner_token: str,
    ) -> EventAnalysisReceiptClaim:
        """Claim one independently durable stage."""
        ...

    async def result(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
    ) -> dict[str, JsonValue]:
        """Load a completed stage result."""
        ...

    async def mark_dispatched(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> bool:
        """Fence the actual provider dispatch."""
        ...

    async def mark_dispatched_with_budget(  # noqa: PLR0913
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
        reservation: LlmBudgetReservation,
        dispatched_at: datetime,
    ) -> bool:
        """Atomically dispatch the event stage and its budget reservation."""
        ...

    async def complete(  # noqa: PLR0913 - durable key and owner fence are independent
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        result_payload: dict[str, JsonValue],
        owner_token: str,
    ) -> bool:
        """Persist the provider result durably."""
        ...

    async def release_unbilled(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> bool:
        """Release a claim proven not to have reached the provider."""
        ...

    async def suppress(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> bool:
        """Persist a terminal zero-call refusal."""
        ...

    async def close(self) -> None:
        """Release repository resources."""
        ...


class EventAnalysisJob(Protocol):
    """Persona analysis path with stage-level durable ownership."""

    async def run_event(
        self,
        pack: EvidencePack,
        *,
        now: datetime,
        receipts: EventAnalysisReceiptRepository,
        cooldown: timedelta,
    ) -> EventAnalysisRun:
        """Run strategist and critic through durable stage receipts."""
        ...


@dataclass(frozen=True, slots=True)
class EventAnalysisDispatcher:
    """Fan one accepted event into configured persona jobs."""

    repository: EventAnalysisReceiptRepository
    jobs: tuple[EventAnalysisJob, ...]
    cooldown: timedelta

    async def dispatch(self, pack: EvidencePack, *, now: datetime) -> EventAnalysisRun:
        """Aggregate every persona without letting one failure block its peer."""
        total = EventAnalysisRun()
        for job in self.jobs:
            try:
                total += await job.run_event(
                    pack,
                    now=now,
                    receipts=self.repository,
                    cooldown=self.cooldown,
                )
            except anyio.get_cancelled_exc_class():
                raise
            except Exception:  # noqa: BLE001 - one persona must not block its peer
                total += EventAnalysisRun(failed=1, reason="persona_failed")
        return total

    async def close(self) -> None:
        """Release the durable receipt repository."""
        with anyio.CancelScope(shield=True):
            await self.repository.close()
