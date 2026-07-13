"""Read-only run-store operations kept separate from claim mutation logic."""

from abc import ABC, abstractmethod

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from quantinue.core.contracts import PipelineRun, RunId
from quantinue.db import postgres_read
from quantinue.db.active_snapshot import ActivePipelineSnapshot
from quantinue.db.contracts import DailyOrderReservation, PersistedAttempt


class PostgresRunReadMixin(ABC):
    """Provide terminal, active, attempt, and reservation read-boundary operations."""

    @property
    @abstractmethod
    def engine(self) -> AsyncEngine:
        """Return the concrete store's configured database engine."""
        raise NotImplementedError

    def _table(self, name: str) -> Table:
        del name
        raise NotImplementedError

    async def get_by_key(self, key: str) -> PipelineRun | None:
        """Return a terminal run, excluding in-progress state."""
        return await postgres_read.get_by_key(self.engine, self._table("pipeline_runs"), key)

    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        """Return durable attempts in insertion order."""
        return await postgres_read.list_attempts(
            self.engine, self._table("pipeline_stage_attempts"), run_id
        )

    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        """Return recent terminal runs."""
        return await postgres_read.list_recent(self.engine, self._table("pipeline_runs"), limit)

    async def list_active(self, limit: int = 20) -> tuple[ActivePipelineSnapshot, ...]:
        """Return current checkpoint snapshots without raw failure messages."""
        return await postgres_read.list_active(
            self.engine,
            self._table("pipeline_runs"),
            self._table("pipeline_stage_attempts"),
            limit,
        )

    async def reserve_daily_new_order(self, request: DailyOrderReservation) -> bool:
        """Atomically reserve a canonical planned order under its daily cap."""
        return await postgres_read.reserve_daily_new_order(
            self.engine,
            self._table("tb_order"),
            self._table("tb_strategist_signals"),
            request,
        )
