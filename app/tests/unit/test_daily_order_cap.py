from datetime import UTC, date, datetime, timedelta

import anyio
import pytest

from quantinue.broker.mock import MockBroker
from quantinue.core.contracts import PipelineRequest
from quantinue.db.contracts import DailyOrderReservation
from quantinue.db.memory import InMemoryRunStore
from quantinue.llm.provider import DeterministicAnalyzer
from quantinue.orchestration.factory import build_roles
from quantinue.orchestration.pipeline import PipelineOrchestrator
from quantinue.orchestration.policy import DEFAULT_PIPELINE_POLICY


def _reservation(identity: int, *, cap: int = 1) -> DailyOrderReservation:
    return DailyOrderReservation(
        account_id=7,
        trade_date=date(2026, 7, 13),
        signal_id=identity,
        idempotency_key=f"q-a7-s{identity}",
        ticker="NVDA",
        quantity=1,
        entry_price=100.0,
        stop_price=85.0,
        take_profit_price=120.0,
        cap=cap,
    )


@pytest.mark.anyio
async def test_memory_daily_cap_allows_only_one_concurrent_new_identity() -> None:
    store = InMemoryRunStore()
    outcomes: list[bool] = []

    async def reserve(identity: int) -> None:
        outcomes.append(await store.reserve_daily_new_order(_reservation(identity)))

    async with anyio.create_task_group() as group:
        _ = group.start_soon(reserve, 101)
        _ = group.start_soon(reserve, 102)

    assert sorted(outcomes) == [False, True]


@pytest.mark.anyio
async def test_memory_daily_cap_is_idempotent_for_same_order_identity() -> None:
    store = InMemoryRunStore()
    request = _reservation(101)

    first = await store.reserve_daily_new_order(request)
    replay = await store.reserve_daily_new_order(request)

    assert first is True
    assert replay is True


@pytest.mark.anyio
async def test_role09_uses_injected_daily_cap_before_role10_submission() -> None:
    store = InMemoryRunStore()
    roles = build_roles(
        DeterministicAnalyzer(),
        MockBroker(),
        store=store,
        policy=DEFAULT_PIPELINE_POLICY.model_copy(update={"daily_new_order_cap": 1}),
    )
    orchestrator = PipelineOrchestrator(roles[:10], store)
    cycle = datetime(2026, 7, 13, 13, 0, tzinfo=UTC)

    first = await orchestrator.run(PipelineRequest(ticker="NVDA", cycle_ts=cycle))
    capped = await orchestrator.run(
        PipelineRequest(ticker="NVDA", cycle_ts=cycle + timedelta(minutes=1))
    )

    assert first.order is not None
    assert capped.order is None
    assert capped.stages[8].summary.startswith("수량 0")
