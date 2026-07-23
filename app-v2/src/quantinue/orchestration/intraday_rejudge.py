"""Shared proposal, critic, and soft-exit path for intraday rejudgement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from quantinue.core.market_calendar import NEW_YORK

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date, datetime
    from decimal import Decimal

    from quantinue.llm.budget import LlmBudgetReservation
    from quantinue.orchestration.work_lease import WorkLease
    from quantinue.roles.analysis.job import AnalysisJob
    from quantinue.roles.exits import ExitDecision


class IntradaySellDomain(Protocol):
    """Ledger reads used after refreshed judgements are persisted."""

    async def approved_sell_profiles(
        self, as_of: date, tickers: tuple[str, ...]
    ) -> Mapping[str, frozenset[str]]:
        """Return personas whose sell survived the critic."""
        ...

    async def claim_rejudgement(
        self,
        ticker: str,
        persona: str,
        *,
        owner_token: str,
        now: datetime,
        cooldown: timedelta,
    ) -> bool:
        """Reserve the shared trigger-independent cooldown."""
        ...

    async def complete_rejudgement(
        self,
        ticker: str,
        persona: str,
        *,
        owner_token: str,
        now: datetime,
    ) -> bool:
        """Publish cooldown for the current owner."""
        ...

    async def dispatch_rejudgement(
        self, ticker: str, persona: str, *, owner_token: str, now: datetime
    ) -> bool:
        """Make the shared cooldown non-reclaimable at provider dispatch."""
        ...

    async def dispatch_rejudgement_with_budget(
        self,
        ticker: str,
        persona: str,
        *,
        owner_token: str,
        reservation: LlmBudgetReservation,
        dispatched_at: datetime,
    ) -> bool:
        """Atomically dispatch cooldown and budget ownership."""
        ...

    async def release_rejudgement(
        self, ticker: str, persona: str, *, owner_token: str
    ) -> bool:
        """Release the caller's pre-result cooldown reservation."""
        ...


class SoftSellExecutor(Protocol):
    """Durable execution seam for critic-approved intraday sells."""

    async def run_soft_sells(
        self,
        *,
        as_of: date,
        prices: Mapping[str, Decimal],
        profiles: Mapping[str, frozenset[str]],
    ) -> tuple[ExitDecision, ...]:
        """Close the matching persona holdings and return durable decisions."""
        ...


class IntradayBuyExecutor(Protocol):
    """Existing allocation contract exposed at an intraday timestamp."""

    async def run_intraday(
        self, *, now: datetime, prices: Mapping[str, Decimal]
    ) -> str:
        """Size and execute the newest approved buys, idempotently."""
        ...


class IntradayPartialFailureError(RuntimeError):
    """Raised when any persona leaves ticker work incomplete."""


@dataclass(frozen=True, slots=True)
class _CooldownLease:
    domain: IntradaySellDomain
    owner_tokens: Mapping[str, str]
    persona: str
    now: datetime
    inner: WorkLease | None

    async def renew(self) -> None:
        if self.inner is not None:
            await self.inner.renew()

    async def claim_item(self, ticker: str, persona: str) -> bool:
        return self.inner is None or await self.inner.claim_item(ticker, persona)

    async def mark_dispatched(self, ticker: str, persona: str) -> None:
        if self.inner is not None:
            await self.inner.mark_dispatched(ticker, persona)
        owner_token = self.owner_tokens[ticker]
        if not await self.domain.dispatch_rejudgement(
            ticker, persona, owner_token=owner_token, now=self.now
        ):
            message = "rejudgement ownership lost before dispatch"
            raise IntradayPartialFailureError(message)

    async def dispatch_with_budget(
        self,
        ticker: str,
        persona: str,
        reservation: LlmBudgetReservation,
        *,
        dispatched_at: datetime,
    ) -> bool:
        if self.inner is not None:
            await self.inner.mark_dispatched(ticker, persona)
        return await self.domain.dispatch_rejudgement_with_budget(
            ticker,
            persona,
            owner_token=self.owner_tokens[ticker],
            reservation=reservation,
            dispatched_at=dispatched_at,
        )

    async def complete_item(self, ticker: str, persona: str) -> None:
        if self.inner is not None:
            await self.inner.complete_item(ticker, persona)

    async def release_item(self, ticker: str, persona: str) -> None:
        if self.inner is not None:
            await self.inner.release_item(ticker, persona)


@dataclass(frozen=True, slots=True)
class IntradayRejudgeEngine:
    """Run both investment personas, then execute approved sell reversals."""

    domain: IntradaySellDomain
    jobs: tuple[AnalysisJob, ...]
    exits: SoftSellExecutor
    allocation: IntradayBuyExecutor | None = None
    cooldown: timedelta = timedelta(minutes=30)

    async def run(  # noqa: C901 - trigger ownership lifecycle
        self,
        *,
        now: datetime,
        prices: Mapping[str, Decimal],
        lease: WorkLease | None = None,
    ) -> int:
        """Refresh triggered tickers and close approved reversals in one tick."""
        mutable_prices = dict(prices)
        skipped = 0
        for job in self.jobs:
            reserved: dict[str, str] = {}
            for ticker in mutable_prices:
                owner_token = uuid4().hex
                if await self.domain.claim_rejudgement(
                    ticker,
                    job.profile_name,
                    owner_token=owner_token,
                    now=now,
                    cooldown=self.cooldown,
                ):
                    reserved[ticker] = owner_token
            try:
                outcome = await job.run_intraday(
                    now=now,
                    prices={
                        ticker: mutable_prices[ticker]
                        for ticker in reserved
                    },
                    lease=_CooldownLease(
                        self.domain, reserved, job.profile_name, now, lease
                    ),
                )
            except BaseException:
                for ticker, owner_token in reserved.items():
                    _ = await self.domain.release_rejudgement(
                        ticker, job.profile_name, owner_token=owner_token
                    )
                raise
            skipped += outcome.skipped
            completed_tickers = frozenset(item.ticker for item in outcome.outcomes)
            for ticker, owner_token in reserved.items():
                if ticker not in completed_tickers:
                    _ = await self.domain.release_rejudgement(
                        ticker, job.profile_name, owner_token=owner_token
                    )
                    continue
                if not await self.domain.complete_rejudgement(
                    ticker,
                    job.profile_name,
                    owner_token=owner_token,
                    now=now,
                ):
                    message = "rejudgement ownership lost"
                    raise IntradayPartialFailureError(message)
        if skipped:
            message = f"intraday rejudgement incomplete: skipped={skipped}"
            raise IntradayPartialFailureError(message)
        as_of = now.astimezone(NEW_YORK).date()
        profiles = await self.domain.approved_sell_profiles(
            as_of, tuple(mutable_prices)
        )
        if lease is not None:
            await lease.renew()
        closed = await self.exits.run_soft_sells(
            as_of=as_of, prices=mutable_prices, profiles=profiles
        )
        if self.allocation is not None:
            if lease is not None:
                await lease.renew()
            _ = await self.allocation.run_intraday(now=now, prices=mutable_prices)
        return len(closed)
