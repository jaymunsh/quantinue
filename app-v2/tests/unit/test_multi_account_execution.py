"""Simulated accounts each execute; a real broker never fans out.

The demo roster is seven internal accounts sharing one process. Iterating them
against a real broker would submit seven orders into the single Alpaca paper
account — seven times the intended position. Fan-out is simulation-only.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from quantinue.broker.mock import MockBroker
from quantinue.broker.provider import OrderPlan
from quantinue.core.contracts import (
    AccountOrderPlan,
    OrderResult,
    PipelineContext,
    PipelineRequest,
)
from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.db.memory import InMemoryRunStore
from quantinue.roles.role_10_order_execution.service import OrderExecution

NOW = datetime(2026, 7, 20, 17, 0, tzinfo=UTC)


class _RecordingRealBroker:
    """Stands in for Alpaca: a single external account behind the adapter."""

    def __init__(self) -> None:
        self._inner = MockBroker()
        self.submitted: list[OrderPlan] = []

    async def submit(self, plan: OrderPlan) -> OrderResult:
        self.submitted.append(plan)
        return await self._inner.submit(plan)


def _plan(account_id: int, quantity: int) -> AccountOrderPlan:
    return AccountOrderPlan(
        account_id=account_id,
        signal_id=account_id,
        decision="planned" if quantity else "skipped",
        quantity=quantity,
        entry_price=100.0,
        stop_loss=85.0,
        take_profit=120.0,
        skipped_reason=None if quantity else "min_cash",
    )


def _context(plans: tuple[AccountOrderPlan, ...]) -> PipelineContext:
    context = PipelineContext(request=PipelineRequest(ticker="NVDA", cycle_ts=NOW))
    stages = context
    for component in ("08", "09"):
        evidence = Evidence(
            evidence_id=f"{context.run_id}:{component}:plan",
            run_id=context.run_id,
            source="policy",
            source_ref=f"policy://{component}/v1",
            observed_at=NOW,
            captured_at=NOW,
            confidence=1.0,
            kind=EvidenceKind.MODEL_OUTPUT,
        )
        stages = stages.add_stage(component, component, "ok", evidence=evidence)
    primary = plans[0] if plans else None
    return replace(
        stages,
        last_price=100.0,
        account_plans=plans,
        account_id=primary.account_id if primary else 1,
        signal_id=primary.signal_id if primary else 1,
        quantity=primary.quantity if primary else 0,
        stop_loss=85.0,
        take_profit=120.0,
    )


@pytest.mark.anyio
async def test_every_funded_simulated_account_gets_its_own_order() -> None:
    plans = (_plan(1, 200), _plan(2, 100), _plan(3, 10))
    service = OrderExecution(MockBroker(), InMemoryRunStore())

    updated = await service.execute(_context(plans))

    assert len(updated.account_orders) == 3
    assert {order.account_id for order in updated.account_orders} == {1, 2, 3}


@pytest.mark.anyio
async def test_a_skipped_account_is_not_submitted() -> None:
    plans = (_plan(1, 200), _plan(2, 0))
    service = OrderExecution(MockBroker(), InMemoryRunStore())

    updated = await service.execute(_context(plans))

    assert {order.account_id for order in updated.account_orders} == {1}


@pytest.mark.anyio
async def test_orders_are_distinct_per_account() -> None:
    # 같은 신호라도 계좌마다 별도 주문이어야 한다 — 멱등키가 겹치면 한 건으로
    # 합쳐져 나머지 계좌가 조용히 체결된 것처럼 보인다.
    plans = (_plan(1, 200), _plan(2, 100))
    service = OrderExecution(MockBroker(), InMemoryRunStore())

    updated = await service.execute(_context(plans))

    client_ids = {order.result.client_order_id for order in updated.account_orders}
    assert len(client_ids) == 2


@pytest.mark.anyio
async def test_a_real_broker_never_fans_out() -> None:
    # 실 브로커 뒤에는 외부 계좌가 하나뿐이다. 7계좌를 순회하면 의도한
    # 포지션의 7배가 그 하나에 쌓인다.
    plans = (_plan(1, 200), _plan(2, 100), _plan(3, 10))
    broker = _RecordingRealBroker()
    service = OrderExecution(broker, InMemoryRunStore())

    updated = await service.execute(_context(plans))

    assert len(broker.submitted) == 1
    assert len(updated.account_orders) == 1
    assert updated.account_orders[0].account_id == 1


@pytest.mark.anyio
async def test_the_scalar_order_still_mirrors_the_primary_account() -> None:
    # role_11과 화면이 아직 스칼라를 읽는다.
    plans = (_plan(1, 200), _plan(2, 100))
    service = OrderExecution(MockBroker(), InMemoryRunStore())

    updated = await service.execute(_context(plans))

    assert updated.order is not None
    assert updated.order.quantity == 200
