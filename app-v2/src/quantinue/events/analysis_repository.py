"""PostgreSQL fences for stage-granular exactly-once event analysis."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from quantinue.events.evidence import EvidencePack


class EventAnalysisStage(StrEnum):
    """Separately billable and durable analysis stages."""

    STRATEGIST = "strategist"
    CRITIC = "critic"


class EventAnalysisReceiptClaim(StrEnum):
    """Durable claim result for one event, ticker, persona, and stage."""

    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"
    SUPPRESSED = "suppressed"
    UNCERTAIN = "uncertain"


class _ReceiptRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    status: str
    dispatched: bool
    result_payload: dict[str, JsonValue] | None


class PostgresEventAnalysisReceiptRepository:
    """Serialize stage claims and fail closed only after provider dispatch."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy pool for the shared event receipt ledger."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        """Dispose all pooled receipt connections."""
        await self._engine.dispose()

    async def claim(  # noqa: PLR0913 - durable key, policy, and owner are independent
        self,
        pack: EvidencePack,
        persona: str,
        stage: EventAnalysisStage,
        now: datetime,
        cooldown: timedelta,
        owner_token: str,
    ) -> EventAnalysisReceiptClaim:
        """Claim one stage, applying event cooldown only to the strategist."""
        event_id = pack.document.event_id
        ticker = pack.document.ticker
        receipt_persona = self._persona(persona, stage)
        async with self._engine.begin() as connection:
            lock_key = (
                f"rejudgement:{ticker}:{persona}"
                if stage is EventAnalysisStage.STRATEGIST
                else f"event-analysis:{event_id}:{receipt_persona}"
            )
            _ = await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": lock_key},
            )
            existing = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT status, completed_at IS NOT NULL AS dispatched,
                                   result_payload
                            FROM tb_event_processing_receipt
                            WHERE event_id=:event_id AND ticker=:ticker
                              AND persona=:persona
                            """
                        ),
                        self._key(event_id, ticker, persona, stage),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                row = _ReceiptRow.model_validate(dict(existing))
                if row.status == "processed":
                    return EventAnalysisReceiptClaim.COMPLETED
                if row.status == "skipped":
                    return EventAnalysisReceiptClaim.SUPPRESSED
                if row.dispatched:
                    return EventAnalysisReceiptClaim.UNCERTAIN
                return EventAnalysisReceiptClaim.DUPLICATE
            cooled = False
            if stage is EventAnalysisStage.STRATEGIST:
                reservation = await connection.execute(
                    text(
                        """
                        INSERT INTO tb_rejudgement_cooldown
                          (ticker, persona, status, owner_token, claimed_at)
                        VALUES
                          (:ticker, :persona, 'claimed', :owner_token, :now)
                        ON CONFLICT (ticker, persona) DO UPDATE
                        SET status='claimed', owner_token=:owner_token,
                            claimed_at=:now, completed_at=NULL
                        WHERE tb_rejudgement_cooldown.status='completed'
                          AND tb_rejudgement_cooldown.completed_at <= :cooldown_after
                        RETURNING ticker
                        """
                    ),
                    {
                        "ticker": ticker,
                        "persona": persona,
                        "owner_token": owner_token,
                        "now": now,
                        "cooldown_after": now - cooldown,
                    },
                )
                cooled = reservation.one_or_none() is None
            status = "skipped" if cooled else "claimed"
            _ = await connection.execute(
                text(
                    """
                    INSERT INTO tb_event_processing_receipt
                      (event_id, ticker, persona, status, owner_token,
                       claimed_at, completed_at)
                    VALUES
                      (:event_id, :ticker, :persona, :status, :owner_token,
                       :claimed_at, :completed_at)
                    """
                ),
                {
                    "event_id": event_id,
                    "ticker": ticker,
                    "persona": receipt_persona,
                    "status": status,
                    "owner_token": owner_token,
                    "claimed_at": now,
                    "completed_at": now if cooled else None,
                },
            )
        if cooled:
            return EventAnalysisReceiptClaim.COOLDOWN
        return EventAnalysisReceiptClaim.CLAIMED

    async def result(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
    ) -> dict[str, JsonValue]:
        """Load the typed JSON payload of a completed stage."""
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT status, completed_at IS NOT NULL AS dispatched,
                                   result_payload
                            FROM tb_event_processing_receipt
                            WHERE event_id=:event_id AND ticker=:ticker
                              AND persona=:persona
                            """
                        ),
                        self._key(event_id, ticker, persona, stage),
                    )
                )
                .mappings()
                .one()
            )
        parsed = _ReceiptRow.model_validate(dict(row))
        if parsed.status != "processed" or parsed.result_payload is None:
            message = "completed event analysis stage has no result payload"
            raise RuntimeError(message)
        return parsed.result_payload

    async def mark_dispatched(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> None:
        """Make a stage non-releasable at the actual provider boundary."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET completed_at=claimed_at
                    WHERE event_id=:event_id AND ticker=:ticker
                      AND persona=:persona AND status='claimed'
                      AND completed_at IS NULL AND owner_token=:owner_token
                    """
                ),
                {**self._key(event_id, ticker, persona, stage), "owner_token": owner_token},
            )
            if stage is EventAnalysisStage.STRATEGIST:
                _ = await connection.execute(
                    text(
                        """
                        UPDATE tb_rejudgement_cooldown
                        SET status='completed', completed_at=claimed_at
                        WHERE ticker=:ticker AND persona=:cooldown_persona
                          AND status='claimed' AND owner_token=:owner_token
                        """
                    ),
                    {
                        "ticker": ticker,
                        "cooldown_persona": persona,
                        "owner_token": owner_token,
                    },
                )

    async def complete(  # noqa: PLR0913 - durable key and owner fence are independent
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        result_payload: dict[str, JsonValue],
        owner_token: str,
    ) -> None:
        """Persist a stage result before the next stage may be claimed."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET status='processed',
                        result_payload=CAST(:result_payload AS JSONB),
                        completed_at=GREATEST(claimed_at, now())
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND status='claimed' AND owner_token=:owner_token
                    """
                ),
                {
                    **self._key(event_id, ticker, persona, stage),
                    "result_payload": json.dumps(result_payload, separators=(",", ":")),
                    "owner_token": owner_token,
                },
            )

    async def release_unbilled(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> None:
        """Delete only a stage proven not to have reached the provider."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    DELETE FROM tb_event_processing_receipt
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND status='claimed' AND completed_at IS NULL
                      AND owner_token=:owner_token
                    """
                ),
                {**self._key(event_id, ticker, persona, stage), "owner_token": owner_token},
            )
            if stage is EventAnalysisStage.STRATEGIST:
                _ = await connection.execute(
                    text(
                        """
                        DELETE FROM tb_rejudgement_cooldown
                        WHERE ticker=:ticker AND persona=:cooldown_persona
                          AND status='claimed' AND owner_token=:owner_token
                        """
                    ),
                    {
                        "ticker": ticker,
                        "cooldown_persona": persona,
                        "owner_token": owner_token,
                    },
                )

    async def suppress(
        self,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
        owner_token: str,
    ) -> None:
        """Record a stage-local budget refusal that made no provider call."""
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text(
                    """
                    UPDATE tb_event_processing_receipt
                    SET status='skipped', completed_at=GREATEST(claimed_at, now())
                    WHERE event_id=:event_id AND ticker=:ticker AND persona=:persona
                      AND owner_token=:owner_token
                      AND status='claimed' AND completed_at IS NULL
                    """
                ),
                {**self._key(event_id, ticker, persona, stage), "owner_token": owner_token},
            )

    @staticmethod
    def _persona(persona: str, stage: EventAnalysisStage) -> str:
        return f"analysis:{persona}:{stage.value}"

    @classmethod
    def _key(
        cls,
        event_id: int,
        ticker: str,
        persona: str,
        stage: EventAnalysisStage,
    ) -> dict[str, int | str]:
        return {
            "event_id": event_id,
            "ticker": ticker,
            "persona": cls._persona(persona, stage),
        }
