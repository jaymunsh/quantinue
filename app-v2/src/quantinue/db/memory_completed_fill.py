"""Shared completed-fill store contract for process-local accounting."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio

from quantinue.db.simulated_portfolio import (
    SimulatedFill,
    SimulatedOrder,
    completed_fill_records,
)

if TYPE_CHECKING:
    from quantinue.db.domain_records import CompletedFillWrite
    from quantinue.db.memory_exposure import AppOrderExposure


class MemoryCompletedFillMixin:
    """Apply completed fills using state owned by the concrete memory store."""

    def __init__(self) -> None:
        """Initialize state shared by exposure and completed-fill accounting."""
        self._lock = anyio.Lock()
        self._app_order_exposures: dict[str, AppOrderExposure] = {}
        self._simulated_fills: dict[str, SimulatedFill] = {}

    async def record_simulated_order(
        self, order: SimulatedOrder, fill: SimulatedFill | None
    ) -> None:
        """Persist the generated local records through the concrete store."""
        del order, fill
        raise NotImplementedError

    async def record_completed_fill(self, value: CompletedFillWrite) -> int:
        """Apply the shared durable completed-fill contract to process-local state."""
        async with self._lock:
            exposure = self._app_order_exposures[value.idempotency_key]
        order, fill = completed_fill_records(
            exposure.request.ticker, exposure.request.entry_price, value
        )
        await self.record_simulated_order(order, fill)
        return len(self._simulated_fills)
