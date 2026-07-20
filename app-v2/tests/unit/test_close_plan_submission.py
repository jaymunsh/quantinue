"""Phase 1b: the simulated engine must be able to execute a close, not just a buy."""

import pytest
from pydantic import ValidationError

from quantinue.broker.contracts import ClosePlan
from quantinue.broker.mock import MockBroker


def _plan(**overrides: object) -> ClosePlan:
    fields: dict[str, object] = {
        "ticker": "NVDA",
        "client_order_id": "q-a1-s7-c",
        "quantity": 2,
        "reference_price": 130.0,
        "closes_client_order_id": "q-a1-s7",
    }
    fields.update(overrides)
    return ClosePlan(**fields)  # pyright: ignore[reportArgumentType]


def test_close_plan_needs_no_bracket_legs() -> None:
    """청산에는 보호 레그가 없다 — 더미 값을 요구하면 원장이 거짓을 담는다."""
    # Given/When
    plan = _plan()

    # Then
    assert plan.closes_client_order_id == "q-a1-s7"


def test_close_plan_must_name_the_entry_it_closes() -> None:
    """실현손익의 짝이 없는 청산은 성과 집계에서 유령이 된다."""
    # Given/When/Then
    with pytest.raises(ValidationError):
        _ = ClosePlan(  # pyright: ignore[reportCallIssue]
            ticker="NVDA",
            client_order_id="q-a1-s7-c",
            quantity=2,
            reference_price=130.0,
        )


@pytest.mark.anyio
async def test_mock_broker_fills_a_close_without_protective_legs() -> None:
    """A simulated close fills at its reference price and opens no new bracket."""
    # Given
    broker = MockBroker()

    # When
    result = await broker.close(_plan())

    # Then
    assert result.status == "filled"
    assert result.quantity == 2
    assert result.filled_avg_price == 130.0
    # 청산이 보호 레그를 만들면 닫은 포지션에 손절이 남아 유령 주문이 된다.
    assert result.stop_leg_order_id is None
    assert result.take_profit_leg_order_id is None


@pytest.mark.anyio
async def test_replaying_the_same_close_returns_the_first_fill() -> None:
    """멱등: 재시도가 두 번째 청산이 되면 없는 주식을 판다."""
    # Given
    broker = MockBroker()

    # When
    first = await broker.close(_plan())
    replayed = await broker.close(_plan())

    # Then
    assert first.order_id == replayed.order_id
