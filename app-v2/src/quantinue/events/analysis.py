"""Exactly-once dispatch boundary for routed event rejudgements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import anyio

from quantinue.events.analysis_repository import EventAnalysisReceiptClaim
from quantinue.llm.budget import LlmBudgetExceededError

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from quantinue.events.evidence import EvidencePack


@dataclass(frozen=True, slots=True)
class EventAnalysisRun:
    """Truthful outcomes from one accepted event fan-out."""

    completed: int = 0
    suppressed: int = 0
    failed: int = 0


class EventAnalysisJob(Protocol):
    """Existing persona analysis path exposed to the event dispatcher."""

    @property
    def profile_name(self) -> str:
        """Return the persona used in durable receipt keys."""
        ...

    async def run_event(self, pack: EvidencePack, *, now: datetime) -> object:
        """Run strategist and critic for one bounded evidence pack."""
        ...


class EventAnalysisReceiptRepository(Protocol):
    """Durable claim and completion operations used by the dispatcher."""

    async def claim(
        self,
        pack: EvidencePack,
        persona: str,
        now: datetime,
        cooldown: timedelta,
    ) -> EventAnalysisReceiptClaim:
        """Claim or durably suppress one persona."""
        ...

    async def mark_charged(self, event_id: int, ticker: str, persona: str) -> None:
        """Fence the provider boundary before a potentially paid call."""
        ...

    async def complete(self, event_id: int, ticker: str, persona: str) -> None:
        """Mark both strategist and critic work durable."""
        ...

    async def release_unbilled(self, event_id: int, ticker: str, persona: str) -> None:
        """Release work proven not to have crossed the provider boundary."""
        ...

    async def suppress(self, event_id: int, ticker: str, persona: str) -> None:
        """Record a budget refusal that made no provider call."""
        ...

    async def close(self) -> None:
        """Release repository resources."""
        ...


@dataclass(frozen=True, slots=True)
class EventAnalysisDispatcher:
    """Fan one accepted event into the existing persona jobs."""

    repository: EventAnalysisReceiptRepository
    jobs: tuple[EventAnalysisJob, ...]
    cooldown: timedelta

    async def dispatch(self, pack: EvidencePack, *, now: datetime) -> EventAnalysisRun:
        """Run every configured persona behind one durable claim."""
        completed = 0
        suppressed = 0
        failed = 0
        for job in self.jobs:
            claim = await self.repository.claim(
                pack, job.profile_name, now, self.cooldown
            )
            if claim is not EventAnalysisReceiptClaim.CLAIMED:
                suppressed += 1
                continue
            charged = False
            try:
                with anyio.CancelScope(shield=True):
                    await self.repository.mark_charged(
                        pack.document.event_id,
                        pack.document.ticker,
                        job.profile_name,
                    )
                    charged = True
                _ = await job.run_event(pack, now=now)
                with anyio.CancelScope(shield=True):
                    await self.repository.complete(
                        pack.document.event_id,
                        pack.document.ticker,
                        job.profile_name,
                    )
                completed += 1
            except anyio.get_cancelled_exc_class():
                if not charged:
                    with anyio.CancelScope(shield=True):
                        await self.repository.release_unbilled(
                            pack.document.event_id,
                            pack.document.ticker,
                            job.profile_name,
                        )
                raise
            except LlmBudgetExceededError:
                with anyio.CancelScope(shield=True):
                    await self.repository.suppress(
                        pack.document.event_id,
                        pack.document.ticker,
                        job.profile_name,
                    )
                suppressed += 1
            except Exception:  # noqa: BLE001 - one persona must not block its peer
                failed += 1
        return EventAnalysisRun(completed, suppressed, failed)

    async def close(self) -> None:
        """Release the durable receipt repository."""
        with anyio.CancelScope(shield=True):
            await self.repository.close()
