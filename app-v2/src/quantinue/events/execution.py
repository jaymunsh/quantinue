"""Route changed event judgements through existing durable order jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from quantinue.core.market_calendar import NEW_YORK

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date, datetime
    from decimal import Decimal

    from quantinue.events.analysis import EventDecision
    from quantinue.roles.exits import ExitDecision


class EventSellExecutor(Protocol):
    """Existing soft-sell execution boundary."""

    async def run_soft_sells(
        self,
        *,
        as_of: date,
        prices: Mapping[str, Decimal],
        profiles: Mapping[str, frozenset[str]],
    ) -> tuple[ExitDecision, ...]:
        """Close only holdings approved by the named personas."""
        ...


class EventBuyExecutor(Protocol):
    """Existing allocation execution boundary filtered to event personas."""

    async def run_event(
        self,
        *,
        now: datetime,
        prices: Mapping[str, Decimal],
        profiles: Mapping[str, frozenset[str]],
    ) -> str:
        """Allocate only the supplied event-approved persona/ticker pairs."""
        ...


@dataclass(frozen=True, slots=True)
class EventDecisionExecutor:
    """Execute only materially changed and critic-approved event decisions."""

    exits: EventSellExecutor
    allocation: EventBuyExecutor

    async def execute(
        self, decisions: tuple[EventDecision, ...], *, now: datetime
    ) -> None:
        """Split approved changes into the existing sell and buy paths."""
        sells = self._approved(decisions, "sell")
        if sells:
            await self.exits.run_soft_sells(
                as_of=now.astimezone(NEW_YORK).date(),
                prices={item.ticker: item.reference_price for item in sells},
                profiles=self._profiles(sells),
            )
        buys = self._approved(decisions, "buy")
        if buys:
            await self.allocation.run_event(
                now=now,
                prices={item.ticker: item.reference_price for item in buys},
                profiles=self._profiles(buys),
            )

    @staticmethod
    def _approved(
        decisions: tuple[EventDecision, ...], side: str
    ) -> tuple[EventDecision, ...]:
        return tuple(
            item
            for item in decisions
            if item.approved and item.changed and item.side == side
        )

    @staticmethod
    def _profiles(
        decisions: tuple[EventDecision, ...],
    ) -> dict[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for item in decisions:
            found.setdefault(item.ticker, set()).add(item.persona)
        return {
            ticker: frozenset(personas) for ticker, personas in found.items()
        }
