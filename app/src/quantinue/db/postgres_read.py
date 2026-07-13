"""Read and order-reservation operations shared by the PostgreSQL run store."""

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from quantinue.core.contracts import PipelineRun, RunId
from quantinue.db.active_snapshot import ActivePipelineSnapshot
from quantinue.db.contracts import DailyOrderReservation, PersistedAttempt
from quantinue.db.postgres_query import (
    active_run_snapshots,
    persisted_attempts,
    recent_terminal_runs,
    reserve_daily_order,
    terminal_run_by_key,
)


async def get_by_key(engine: AsyncEngine, runs: Table, key: str) -> PipelineRun | None:
    """Return a terminal run, excluding in-progress state."""
    return await terminal_run_by_key(engine, runs, key)


async def list_attempts(
    engine: AsyncEngine, attempts: Table, run_id: RunId
) -> tuple[PersistedAttempt, ...]:
    """Return durable attempts in insertion order."""
    return await persisted_attempts(engine, attempts, run_id)


async def list_recent(engine: AsyncEngine, runs: Table, limit: int = 20) -> tuple[PipelineRun, ...]:
    """Return recent terminal runs."""
    return await recent_terminal_runs(engine, runs, limit)


async def list_active(
    engine: AsyncEngine, runs: Table, attempts: Table, limit: int = 20
) -> tuple[ActivePipelineSnapshot, ...]:
    """Return current safe snapshots derived from checkpoint contexts."""
    return await active_run_snapshots(engine, runs, attempts, limit)


async def reserve_daily_new_order(
    engine: AsyncEngine, orders: Table, signals: Table, request: DailyOrderReservation
) -> bool:
    """Count and insert a planned order under an account/day transaction lock."""
    async with engine.begin() as connection:
        return await reserve_daily_order(
            connection,
            orders,
            signals,
            request,
        )
