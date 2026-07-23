from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quantinue.events.analysis import EventDecision
from quantinue.events.execution import EventDecisionExecutor


class _Exits:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Decimal], dict[str, frozenset[str]]]] = []

    async def run_soft_sells(
        self,
        *,
        as_of: date,
        prices: Mapping[str, Decimal],
        profiles: Mapping[str, frozenset[str]],
    ) -> tuple[()]:
        _ = as_of
        self.calls.append((dict(prices), dict(profiles)))
        return ()


class _Allocation:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Decimal], dict[str, frozenset[str]]]] = []

    async def run_event(
        self,
        *,
        now: datetime,
        prices: Mapping[str, Decimal],
        profiles: Mapping[str, frozenset[str]],
    ) -> str:
        _ = now
        self.calls.append((dict(prices), dict(profiles)))
        return "1 bought, 0 skipped"


@pytest.mark.anyio
async def test_only_changed_approved_buy_and_sell_reach_execution() -> None:
    exits = _Exits()
    allocation = _Allocation()
    executor = EventDecisionExecutor(exits=exits, allocation=allocation)
    now = datetime(2026, 7, 24, 15, tzinfo=UTC)

    await executor.execute(
        (
            EventDecision(
                ticker="SELL",
                persona="aggressive",
                side="sell",
                reference_price=Decimal(10),
                approved=True,
                changed=True,
            ),
            EventDecision(
                ticker="BUY",
                persona="conservative",
                side="buy",
                reference_price=Decimal(20),
                approved=True,
                changed=True,
            ),
            EventDecision(
                ticker="HOLD",
                persona="aggressive",
                side="hold",
                reference_price=Decimal(30),
                approved=True,
                changed=True,
            ),
            EventDecision(
                ticker="SAME",
                persona="aggressive",
                side="sell",
                reference_price=Decimal(40),
                approved=True,
                changed=False,
            ),
            EventDecision(
                ticker="NO",
                persona="aggressive",
                side="buy",
                reference_price=Decimal(50),
                approved=False,
                changed=True,
            ),
        ),
        now=now,
    )

    assert exits.calls == [
        ({"SELL": Decimal(10)}, {"SELL": frozenset({"aggressive"})})
    ]
    assert allocation.calls == [
        ({"BUY": Decimal(20)}, {"BUY": frozenset({"conservative"})})
    ]


@pytest.mark.anyio
async def test_empty_or_duplicate_decisions_produce_no_execution() -> None:
    exits = _Exits()
    allocation = _Allocation()
    executor = EventDecisionExecutor(exits=exits, allocation=allocation)

    await executor.execute((), now=datetime(2026, 7, 24, 15, tzinfo=UTC))

    assert exits.calls == []
    assert allocation.calls == []
