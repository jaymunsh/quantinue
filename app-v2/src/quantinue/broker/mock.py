"""Deterministic network-free broker adapter."""

from hashlib import sha256
from typing import assert_never

from quantinue.broker.contracts import ClosePlan, OrderPlan
from quantinue.broker.reservations import (
    CompletedClaim,
    InFlightClaim,
    InMemoryOrderReservations,
    OrderReservations,
    OwnerClaim,
)
from quantinue.core.contracts import OrderResult
from quantinue.core.errors import TransientFailureError


class MockBroker:
    """Network-free deterministic fill simulator."""

    def __init__(
        self,
        reservations: OrderReservations | None = None,
        halted_tickers: frozenset[str] = frozenset(),
    ) -> None:
        """Use a private reservation adapter unless one is shared explicitly."""
        self._reservations = reservations or InMemoryOrderReservations()
        self._halted = frozenset(ticker.upper() for ticker in halted_tickers)

    async def is_tradable(self, ticker: str) -> bool:
        """Mirror the venue capability so the halted guard is reachable offline.

        Without this the guard cannot fire in any dry run: role 10 asks only
        brokers that advertise the capability.
        """
        return ticker.upper() not in self._halted

    async def submit(self, plan: OrderPlan) -> OrderResult:
        """Return and cache an immediate full fill with resting protective legs."""
        return await self._fill_once(
            client_order_id=plan.client_order_id,
            quantity=plan.quantity,
            price=plan.entry_price,
            with_protective_legs=True,
        )

    async def close(self, plan: ClosePlan) -> OrderResult:
        """Simulate an exit at the reference price, opening no new protection.

        청산이 보호 레그를 만들면 이미 닫은 포지션에 손절 주문이 남아 유령이
        된다 — 그래서 with_protective_legs=False다.
        """
        return await self._fill_once(
            client_order_id=plan.client_order_id,
            quantity=plan.quantity,
            price=plan.reference_price,
            with_protective_legs=False,
        )

    async def _fill_once(
        self,
        *,
        client_order_id: str,
        quantity: int,
        price: float,
        with_protective_legs: bool,
    ) -> OrderResult:
        """Claim the key once and publish a deterministic full fill.

        멱등이 핵심이다. 재시도가 두 번째 체결이 되면 매수는 포지션이 두 배가
        되고 청산은 갖고 있지도 않은 주식을 판다.
        """
        claim = await self._reservations.claim(client_order_id)
        match claim:
            case CompletedClaim(result=result):
                return result
            case InFlightClaim():
                completed = await self._reservations.wait(client_order_id, 1.0)
                if completed is not None:
                    return completed
                provider = "mock"
                reason = "reservation owner did not complete"
                raise TransientFailureError(provider, reason)
            case OwnerClaim(owner_token=owner_token):
                digest = sha256(client_order_id.encode()).hexdigest()[:12]
            case unreachable:
                assert_never(unreachable)
        result = OrderResult(
            order_id=f"mock-{digest}",
            client_order_id=client_order_id,
            status="filled",
            quantity=quantity,
            filled_avg_price=price,
            parent_order_id=f"mock-{digest}",
            stop_leg_order_id=f"mock-{digest}-stop" if with_protective_legs else None,
            take_profit_leg_order_id=(
                f"mock-{digest}-take-profit" if with_protective_legs else None
            ),
        )
        published = await self._reservations.complete(client_order_id, owner_token, result)
        if published:
            return result
        winner = await self._reservations.wait(client_order_id, 0)
        if winner is not None:
            return winner
        provider = "mock"
        reason = "reservation generation changed without a completed result"
        raise TransientFailureError(provider, reason)
