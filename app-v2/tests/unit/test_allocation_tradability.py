"""A new buy must pass a final, bounded venue tradability check."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

import anyio
import pytest

from quantinue.broker.contracts import OrderPlan, OrderResult
from quantinue.core.errors import TransientFailureError
from quantinue.db.contracts import (
    AppOrderExposureReservationOutcome,
    AppOrderExposureReservationResult,
    AppOrderExposureSummary,
)
from quantinue.orchestration.policy import AllocationConfig, GatesConfig
from quantinue.roles.allocation.job import AllocationJob
from quantinue.roles.role_09_risk_portfolio.contracts import RiskPortfolioOutput


@dataclass(slots=True)
class _Domain:
    fills: list[object]

    async def record_completed_fill(self, fill: object) -> bool:
        self.fills.append(fill)
        return True


@dataclass(slots=True)
class _Store:
    domain: _Domain
    reservations: int = 0

    async def reserve_daily_new_order(
        self, _reservation: object
    ) -> AppOrderExposureReservationResult:
        self.reservations += 1
        return AppOrderExposureReservationResult(
            outcome=AppOrderExposureReservationOutcome.ACQUIRED,
            summary=AppOrderExposureSummary(
                account_id=1,
                cap=Decimal(1000),
                planned_or_reserved=Decimal(100),
                remaining=Decimal(900),
            ),
        )


class _Broker:
    def __init__(
        self,
        outcomes: list[bool | Literal["error", "timeout"]],
    ) -> None:
        self._outcomes = outcomes
        self.orders: list[OrderPlan] = []

    async def is_tradable(self, ticker: str) -> bool:
        del ticker
        outcome = self._outcomes.pop(0)
        match outcome:
            case True | False:
                return outcome
            case "error":
                provider = "fake"
                reason = "asset lookup failed"
                raise TransientFailureError(provider, reason)
            case "timeout":
                await anyio.sleep_forever()
                return False

    async def submit(self, plan: OrderPlan) -> OrderResult:
        self.orders.append(plan)
        return OrderResult(
            order_id="fake-order",
            client_order_id=plan.client_order_id,
            status="filled",
            quantity=plan.quantity,
            filled_avg_price=plan.entry_price,
        )


def _plan(ticker: str = "NVDA") -> RiskPortfolioOutput:
    return RiskPortfolioOutput(
        run_id="allocation:race",
        signal_id=7,
        account_id=1,
        ticker=ticker,
        decision="planned",
        quantity=2,
        entry_price=100,
        stop_loss=85,
        take_profit=120,
        skipped_reason=None,
        evidence_ids=("evidence",),
    )


def _job(broker: _Broker, store: _Store) -> AllocationJob:
    return AllocationJob(
        store=store,
        broker=broker,
        profiles={},
        gates=GatesConfig(),
        allocation=AllocationConfig(),
        tradability_timeout_seconds=0.01,
    )


@pytest.mark.anyio
async def test_new_buy_is_blocked_when_tradability_flips_after_selection() -> None:
    # Given
    broker = _Broker([True, False])
    store = _Store(_Domain([]))
    assert await broker.is_tradable("NVDA") is True

    # When
    outcome = await _job(broker, store).execute_buy(
        _plan(), Decimal(1000), date(2026, 7, 23), datetime.now(UTC)
    )

    # Then
    assert outcome.skipped_reason == "not_tradable"
    assert broker.orders == []
    assert store.domain.fills == []
    assert store.reservations == 0


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", [False, "error", "timeout"])
async def test_new_buy_fails_closed_when_final_check_is_unavailable(
    outcome: Literal[False, "error", "timeout"],
) -> None:
    # Given
    broker = _Broker([outcome])
    store = _Store(_Domain([]))

    # When
    result = await _job(broker, store).execute_buy(
        _plan("UNKNOWN"), Decimal(1000), date(2026, 7, 23), datetime.now(UTC)
    )

    # Then
    assert result.executed is False
    assert broker.orders == []
    assert store.domain.fills == []
    assert store.reservations == 0


@pytest.mark.anyio
async def test_tradable_new_buy_uses_existing_idempotent_submit_once() -> None:
    # Given
    broker = _Broker([True])
    store = _Store(_Domain([]))

    # When
    outcome = await _job(broker, store).execute_buy(
        _plan(), Decimal(1000), date(2026, 7, 23), datetime.now(UTC)
    )

    # Then
    assert outcome.executed is True
    assert len(broker.orders) == 1
    assert len(store.domain.fills) == 1
    assert store.reservations == 1


@pytest.mark.anyio
async def test_outer_cancellation_is_not_converted_to_tradability_skip() -> None:
    # Given
    broker = _Broker(["timeout"])
    store = _Store(_Domain([]))

    # When
    with anyio.move_on_after(0) as scope:
        _ = await _job(broker, store).execute_buy(
            _plan(), Decimal(1000), date(2026, 7, 23), datetime.now(UTC)
        )

    # Then
    assert scope.cancelled_caught is True
    assert broker.orders == []
