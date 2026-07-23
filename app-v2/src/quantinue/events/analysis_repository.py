"""PostgreSQL fences for exactly-once event analysis."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from quantinue.events.evidence import EvidencePack


class EventAnalysisReceiptClaim(StrEnum):
    """Durable claim result for one event, ticker, and persona."""

    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    COOLDOWN = "cooldown"


class _ReceiptStatusRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    status: str


class _BooleanRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    value: bool


class PostgresEventAnalysisReceiptRepository:
    """Serialize persona claims and fail closed after a charged boundary."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy pool for the shared event receipt ledger."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        """Dispose all pooled receipt connections."""
        await self._engine.dispose()

    async def claim(
        self,
        pack: EvidencePack,
        persona: str,
        now: datetime,
        cooldown: timedelta,
    ) -> EventAnalysisReceiptClaim:
        """Create one claim, recording cooldown as a terminal suppression."""
        event_id = pack.document.event_id
        ticker = pack.document.ticker
        receipt_persona = self._persona(persona)
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"event-analysis:{event_id}:{receipt_persona}"},
            )
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT status
                            FROM tb_event_processing_receipt
                            WHERE event_id=:event_id AND ticker=:ticker
                              AND persona=:persona
                            """
                        ),
                        {
                            "event_id": event_id,
                            "ticker": ticker,
                            "persona": receipt_persona,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                _ = _ReceiptStatusRow.model_validate(dict(existing))
                return EventAnalysisReceiptClaim.DUPLICATE
            cooled = _BooleanRow.model_validate(
                dict(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT EXISTS (
                                  SELECT 1 FROM tb_event_processing_receipt
                                  WHERE ticker=:ticker AND persona=:persona
                                    AND status='processed'
                                    AND completed_at > :cooldown_after
                                ) AS value
                                """
                            ),
                            {
                                "ticker": ticker,
                                "persona": receipt_persona,
                                "cooldown_after": now - cooldown,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
            ).value
            status = "skipped" if cooled else "claimed"
            _ = await connection.execute(
                text(
                    """
                    INSERT INTO tb_event_processing_receipt
                      (event_id, ticker, persona, status, claimed_at, completed_at)
                    VALUES
                      (:event_id, :ticker, :persona, :status, :claimed_at, :completed_at)
                    """
                ),
                {
                    "event_id": event_id,
                    "ticker": ticker,
                    "persona": receipt_persona,
                    "status": status,
                    "claimed_at": now,
                    "completed_at": now if cooled else None,
                },
            )
        return (
            EventAnalysisReceiptClaim.COOLDOWN
            if cooled
            else EventAnalysisReceiptClaim.CLAIMED
        )

    async def mark_charged(self, event_id: int, ticker: str, persona: str) -> None:
        """Make a claimed receipt non-releasable before provider dispatch."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET completed_at=claimed_at
                    WHERE event_id=:event_id AND ticker=:ticker
                      AND persona=:persona AND status='claimed'
                      AND completed_at IS NULL
                    """
                ),
                self._key(event_id, ticker, persona),
            )

    async def complete(self, event_id: int, ticker: str, persona: str) -> None:
        """Make a charged claim terminal after both results are durable."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET status='processed',
                        completed_at=GREATEST(claimed_at, now())
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND status='claimed'
                    """
                ),
                self._key(event_id, ticker, persona),
            )

    async def release_unbilled(self, event_id: int, ticker: str, persona: str) -> None:
        """Delete only a claim proven not to have reached the provider."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    DELETE FROM tb_event_processing_receipt
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND status='claimed' AND completed_at IS NULL
                    """
                ),
                self._key(event_id, ticker, persona),
            )

    async def suppress(self, event_id: int, ticker: str, persona: str) -> None:
        """Record a budget refusal that made no provider call."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET status='skipped', completed_at=GREATEST(claimed_at, now())
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND status='claimed'
                    """
                ),
                self._key(event_id, ticker, persona),
            )

    @staticmethod
    def _persona(persona: str) -> str:
        return f"analysis:{persona}"

    @classmethod
    def _key(cls, event_id: int, ticker: str, persona: str) -> dict[str, int | str]:
        return {
            "event_id": event_id,
            "ticker": ticker,
            "persona": cls._persona(persona),
        }
