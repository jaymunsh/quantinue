"""Spend ledger and the budget guard that precedes every billable model call."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

import anyio
from pydantic import BaseModel, ConfigDict, Field

from quantinue.llm.provider import ModelInput

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from quantinue.llm.provider import (
        AnalysisResult,
        AnalysisTask,
        LlmAnalyzer,
    )
    from quantinue.llm.usage_limits import MaximumTokenUsage


class LlmBudgetExceededError(RuntimeError):
    """Raised instead of making a call the day's budget cannot pay for."""


class LlmUsageBoundExceededError(RuntimeError):
    """Raised after recording usage that violated its provider-enforced bound."""


class LlmUsageMissingError(RuntimeError):
    """Raised after conservatively charging a billable call with missing usage."""


class ModelPrice(BaseModel):
    """Per-million-token rates for one model, owned by config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_usd_per_1m: Decimal = Field(gt=0, allow_inf_nan=False)
    output_usd_per_1m: Decimal = Field(gt=0, allow_inf_nan=False)


class LlmUsageRecord(BaseModel):
    """One row of the tb_llm_usage ledger."""

    model_config = ConfigDict(frozen=True)

    called_at: datetime
    task: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    est_cost_usd: Decimal = Field(ge=0)
    run_id: str | None = None


def require_pricing_for(model: str, pricing: Mapping[str, ModelPrice]) -> None:
    """Refuse to start a billable provider whose model has no declared rate.

    fail-closed다. 요율이 없으면 ``_cost``가 늘 0을 내고, 0만 쌓이는 원장은
    상한을 영원히 안 넘긴다 — 예산이 있는 척하면서 없는 상태가 된다.
    모델명을 바꾸고 config를 안 고친 순간이 정확히 그 상태이므로, 기동에서 막는다.
    """
    if model not in pricing:
        message = (
            f"no model_pricing declared for billable model {model!r} "
            "— add it under mvp2.budget.model_pricing"
        )
        raise ValueError(message)


class LlmUsageLedger(Protocol):
    """Narrow spend-ledger capability used by the budget guard."""

    async def llm_spend_on(self, day: date) -> Decimal:
        """Return the total estimated spend recorded for that calendar day."""
        ...

    async def record_llm_usage(self, record: LlmUsageRecord) -> None:
        """Append one call to the ledger."""
        ...


class LlmBudgetReservation(BaseModel):
    """One owner-fenced admission to the daily provider budget."""

    model_config = ConfigDict(frozen=True)
    budget_day: date
    reservation_id: str
    owner_token: str
    max_cost_usd: Decimal


@runtime_checkable
class AtomicLlmBudgetReservations(Protocol):
    """Durable multi-process admission and settlement contract."""

    async def reserve_llm_budget(  # noqa: PLR0913
        self,
        *,
        reservation_id: str,
        owner_token: str,
        budget_day: date,
        reserve_class: str,
        max_cost_usd: Decimal,
        spending_limit: Decimal,
        claimed_at: datetime,
    ) -> LlmBudgetReservation | None:
        """Atomically admit one maximum-cost reservation."""
        ...

    async def dispatch_llm_budget(
        self, reservation: LlmBudgetReservation, *, dispatched_at: datetime
    ) -> bool:
        """Acknowledge the reservation's paid boundary."""
        ...

    async def release_llm_budget(
        self, reservation: LlmBudgetReservation, *, released_at: datetime
    ) -> bool:
        """Release an unbilled reservation owned by the caller."""
        ...

    async def settle_llm_budget(
        self, reservation: LlmBudgetReservation, record: LlmUsageRecord
    ) -> bool:
        """Atomically settle ownership and append actual usage."""
        ...

class PaidCallBoundary(Protocol):
    """Durable callback invoked immediately before a provider call."""

    async def dispatched(self) -> None:
        """Persist the point after which cancellation is billing-ambiguous."""
        ...


class BudgetedAnalyzer:
    """Wraps an analyzer so every billable call is counted and capped."""

    def __init__(  # noqa: PLR0913 - 한 가드는 원장·한도·예약·요율·시계를 함께 소유한다.
        self,
        inner: LlmAnalyzer,
        *,
        ledger: LlmUsageLedger,
        daily_limit_usd: float,
        sell_budget_reserve_ratio: float = 0.0,
        pricing: dict[str, ModelPrice],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Store the wrapped analyzer and the ceiling it must respect."""
        self._inner = inner
        self._ledger = ledger
        self._limit = Decimal(str(daily_limit_usd))
        self._general_limit = self._limit * (Decimal(1) - Decimal(str(sell_budget_reserve_ratio)))
        self._pricing = pricing
        self._now = now
        self._spend_lock = anyio.Lock()
        self._reserved_by_day: dict[date, Decimal] = {}
        self._committed_by_day: dict[date, Decimal] = {}

    @property
    def reserved_usd(self) -> Decimal:
        """Return process-local spend currently reserved by in-flight calls."""
        return sum(self._reserved_by_day.values(), Decimal(0))

    def maximum_usage(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> MaximumTokenUsage:
        """Expose the wrapped provider's enforceable usage ceiling."""
        return self._inner.maximum_usage(task, prompt, profile=profile)

    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        """Refuse, or run the wrapped call and write what it cost to the ledger."""
        return await self._analyze(
            task,
            prompt,
            profile=profile,
            spending_limit=self._general_limit,
            boundary=None,
        )

    async def analyze_reserved(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        """Use the sell-only reserve for a holding rejudgement call."""
        return await self._analyze(
            task,
            prompt,
            profile=profile,
            spending_limit=self._limit,
            boundary=None,
        )

    async def analyze_with_boundary(
        self,
        task: AnalysisTask,
        prompt: str,
        *,
        profile: str | None,
        boundary: PaidCallBoundary,
    ) -> AnalysisResult:
        """Run a general-budget call with a durable provider-boundary callback."""
        return await self._analyze(
            task,
            prompt,
            profile=profile,
            spending_limit=self._general_limit,
            boundary=boundary,
        )

    async def analyze_reserved_with_boundary(
        self,
        task: AnalysisTask,
        prompt: str,
        *,
        profile: str | None,
        boundary: PaidCallBoundary,
    ) -> AnalysisResult:
        """Run a reserve-eligible call with a durable provider-boundary callback."""
        return await self._analyze(
            task,
            prompt,
            profile=profile,
            spending_limit=self._limit,
            boundary=boundary,
        )

    async def _analyze(  # noqa: C901, PLR0912, PLR0915
        self,
        task: AnalysisTask,
        prompt: str,
        *,
        profile: str | None,
        spending_limit: Decimal,
        boundary: PaidCallBoundary | None,
    ) -> AnalysisResult:
        _ = ModelInput(external_data=prompt)
        called_at = self._now()
        day = called_at.date()
        maximum = self.maximum_usage(task, prompt, profile=profile)
        reservation = self._usage_cost(maximum)
        durable = self._ledger if isinstance(self._ledger, AtomicLlmBudgetReservations) else None
        durable_reservation: LlmBudgetReservation | None = None
        if durable is not None:
            durable_reservation = await durable.reserve_llm_budget(
                reservation_id=uuid4().hex,
                owner_token=uuid4().hex,
                budget_day=day,
                reserve_class="sell" if spending_limit == self._limit else "general",
                max_cost_usd=reservation,
                spending_limit=spending_limit,
                claimed_at=called_at,
            )
            if durable_reservation is None:
                message = "daily llm budget exhausted"
                raise LlmBudgetExceededError(message)
        else:
            await self._reserve_local(day, reservation, spending_limit)

        reservation_active = True
        dispatched = False
        try:
            with anyio.CancelScope(shield=True):
                if boundary is not None:
                    await boundary.dispatched()
                if durable is not None and durable_reservation is not None:
                    if not await durable.dispatch_llm_budget(
                        durable_reservation, dispatched_at=called_at
                    ):
                        message = "llm budget reservation ownership lost"
                        raise LlmBudgetExceededError(message)
                    dispatched = True
            result = await self._inner.analyze(task, prompt, profile=profile)
            usage = result.usage
            if usage is None:
                if reservation == 0:
                    return result
                with anyio.CancelScope(shield=True):
                    async with self._spend_lock:
                        missing_record = LlmUsageRecord(
                                called_at=called_at,
                                task=task.value,
                                model=maximum.model,
                                prompt_tokens=maximum.input_tokens,
                                completion_tokens=maximum.output_tokens,
                                est_cost_usd=reservation,
                            )
                        if durable is not None and durable_reservation is not None:
                            if not await durable.settle_llm_budget(
                                durable_reservation, missing_record
                            ):
                                message = "llm budget settlement ownership lost"
                                raise LlmBudgetExceededError(message)
                        else:
                            await self._ledger.record_llm_usage(missing_record)
                        if durable is None:
                            self._committed_by_day[day] += reservation
                            self._release(day, reservation)
                        reservation_active = False
                message = (
                    "provider omitted usage for a billable call; "
                    f"charged reserved maximum {reservation}"
                )
                raise LlmUsageMissingError(message)
            model = result.metadata.model
            cost = self._cost(model, usage.input_tokens, usage.output_tokens)
            with anyio.CancelScope(shield=True):
                async with self._spend_lock:
                    usage_record = LlmUsageRecord(
                            called_at=called_at,
                            task=task.value,
                            model=model,
                            prompt_tokens=usage.input_tokens,
                            completion_tokens=usage.output_tokens,
                            est_cost_usd=cost,
                        )
                    if durable is not None and durable_reservation is not None:
                        if not await durable.settle_llm_budget(durable_reservation, usage_record):
                            message = "llm budget settlement ownership lost"
                            raise LlmBudgetExceededError(message)
                    else:
                        await self._ledger.record_llm_usage(usage_record)
                    if durable is None:
                        self._committed_by_day[day] += cost
                        self._release(day, reservation)
                    reservation_active = False
            if cost > reservation:
                message = f"provider usage cost {cost} exceeded reserved maximum {reservation}"
                raise LlmUsageBoundExceededError(message)
            return result
        finally:
            if reservation_active:
                with anyio.CancelScope(shield=True):
                    if durable is not None and durable_reservation is not None:
                        if dispatched:
                            _ = await durable.settle_llm_budget(
                                durable_reservation,
                                LlmUsageRecord(
                                    called_at=called_at,
                                    task=task.value,
                                    model=maximum.model,
                                    prompt_tokens=maximum.input_tokens,
                                    completion_tokens=maximum.output_tokens,
                                    est_cost_usd=reservation,
                                ),
                            )
                        else:
                            _ = await durable.release_llm_budget(
                                durable_reservation, released_at=self._now()
                            )
                    else:
                        async with self._spend_lock:
                            self._release(day, reservation)

    async def _reserve_local(
        self, day: date, reservation: Decimal, spending_limit: Decimal
    ) -> None:
        async with self._spend_lock:
            ledger_committed = await self._ledger.llm_spend_on(day)
            committed = max(ledger_committed, self._committed_by_day.get(day, Decimal(0)))
            self._committed_by_day[day] = committed
            reserved = self._reserved_by_day.get(day, Decimal(0))
            if committed + reserved + reservation > spending_limit:
                message = "daily llm budget exhausted"
                raise LlmBudgetExceededError(message)
            self._reserved_by_day[day] = reserved + reservation

    def _release(self, day: date, amount: Decimal) -> None:
        remaining = self._reserved_by_day[day] - amount
        if remaining == 0:
            del self._reserved_by_day[day]
        else:
            self._reserved_by_day[day] = remaining

    def _cost(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        """Estimate one call's cost from the configured per-model rates.

        요율이 없는 모델은 0이다 — 로컬 LLM이 실제로 공짜라 그게 정직한 값이고,
        그래서 openai 모드에서 요율 선언을 빠뜨리면 예산이 조용히 풀린다.
        그 구멍은 기동 시점 검증이 막는다(``require_pricing_for``).
        """
        price = self._pricing.get(model)
        if price is None:
            return Decimal(0)
        per_million = Decimal(1_000_000)
        return (
            Decimal(input_tokens) * price.input_usd_per_1m / per_million
            + Decimal(output_tokens) * price.output_usd_per_1m / per_million
        )

    def _usage_cost(self, usage: MaximumTokenUsage) -> Decimal:
        return self._cost(usage.model, usage.input_tokens, usage.output_tokens)
