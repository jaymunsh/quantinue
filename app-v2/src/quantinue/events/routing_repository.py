"""PostgreSQL boundary for deterministic event routing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from quantinue.events.routing import (
    AcceptedRoute,
    EventCandidate,
    RejectedRoute,
    RoutingDecision,
    route_candidate,
)

if TYPE_CHECKING:
    from datetime import date


class _BooleanValue(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    value: bool


class _TickerValue(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    ticker: str


class _AcceptedRouteRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    event_id: int
    raw_version_id: int
    content_hash: str
    source_name: str
    source_sequence: str
    ticker: str
    event_type: str


@dataclass(frozen=True, slots=True)
class RoutingRun:
    """Durable routing decisions created during one pass."""

    accepted: int
    rejected: int


class PostgresEventRoutingRepository:
    """Read raw-version candidates and append body-free routing receipts."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy PostgreSQL engine."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        """Dispose all pooled database connections."""
        await self._engine.dispose()

    async def pending_candidates(self) -> tuple[EventCandidate, ...]:
        """Return immutable events that have no prior routing decision."""
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT event.event_id, event.raw_version_id,
                               version.content_hash, event.source_name,
                               document.source_url, event.source_sequence,
                               event.event_type, event.occurred_at,
                               event.payload->>'ticker' AS ticker,
                               version.raw_text
                        FROM tb_normalized_event AS event
                        JOIN tb_event_raw_version AS version USING (raw_version_id)
                        JOIN tb_event_raw_document AS document USING (document_id)
                        WHERE NOT EXISTS (
                          SELECT 1
                          FROM tb_event_processing_receipt AS receipt
                          WHERE receipt.event_id = event.event_id
                            AND receipt.persona LIKE 'routing:%'
                        )
                        ORDER BY event.occurred_at, event.event_id
                        """
                    )
                )
            ).mappings()
        return tuple(EventCandidate.model_validate(dict(row)) for row in rows)

    async def scope_tickers(self, as_of: date) -> frozenset[str]:
        """Read the canonical daily scope, which already includes held backfills."""
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT ticker
                        FROM tb_daily_pick
                        WHERE trade_date = :as_of
                        ORDER BY ticker
                        """
                    ),
                    {"as_of": as_of},
                )
            ).mappings()
        return frozenset(
            _TickerValue.model_validate(dict(row)).ticker for row in rows
        )

    async def accepted_without_evidence(self) -> tuple[AcceptedRoute, ...]:
        """Return accepted immutable versions whose evidence is not durable yet."""
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT event.event_id, event.raw_version_id,
                               version.content_hash, event.source_name,
                               event.source_sequence,
                               receipt.ticker,
                               replace(receipt.persona, 'routing:accepted:', '')
                                 AS event_type
                        FROM tb_normalized_event AS event
                        JOIN tb_event_raw_version AS version USING (raw_version_id)
                        JOIN tb_event_processing_receipt AS receipt USING (event_id)
                        WHERE receipt.persona LIKE 'routing:accepted:%'
                          AND NOT EXISTS (
                            SELECT 1 FROM tb_event_evidence_pack AS evidence
                            WHERE evidence.event_id = event.event_id
                              AND evidence.raw_version_id = event.raw_version_id
                          )
                        ORDER BY event.occurred_at, event.event_id
                        """
                    )
                )
            ).mappings()
        parsed = tuple(
            _AcceptedRouteRow.model_validate(dict(row)) for row in rows
        )
        return tuple(
            AcceptedRoute(
                event_id=row.event_id,
                raw_version_id=row.raw_version_id,
                content_hash=row.content_hash,
                source_name=row.source_name,
                source_sequence=row.source_sequence,
                ticker=row.ticker,
                event_type=row.event_type,
            )
            for row in parsed
        )

    async def record(self, decision: RoutingDecision, ticker: str) -> bool:
        """Append one decision after serializing concurrent attempts per event."""
        match decision:
            case AcceptedRoute(event_type=event_type):
                persona = f"routing:accepted:{event_type}"
                status = "processed"
                stored_ticker = ticker
            case RejectedRoute(reason=reason):
                persona = f"routing:{reason.value}"
                status = "skipped"
                stored_ticker = ticker if ticker.strip() else "UNROUTED"
            case unreachable:
                assert_never(unreachable)
        async with self._engine.begin() as connection:
            _ = await connection.execute(
                text("SELECT pg_advisory_xact_lock(:event_id)"),
                {"event_id": decision.event_id},
            )
            existing = _BooleanValue.model_validate(
                dict(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT EXISTS (
                                  SELECT 1
                                  FROM tb_event_processing_receipt
                                  WHERE event_id = :event_id
                                    AND persona LIKE 'routing:%'
                                ) AS value
                                """
                            ),
                            {"event_id": decision.event_id},
                        )
                    ).mappings().one()
                )
            ).value
            if existing:
                return False
            _ = await connection.execute(
                text(
                    """
                    INSERT INTO tb_event_processing_receipt
                      (event_id, ticker, persona, status, completed_at)
                    VALUES (:event_id, :ticker, :persona, :status, now())
                    """
                ),
                {
                    "event_id": decision.event_id,
                    "ticker": stored_ticker,
                    "persona": persona,
                    "status": status,
                },
            )
        return True


async def route_pending_events(
    repository: PostgresEventRoutingRepository,
    as_of: date,
) -> RoutingRun:
    """Persist deterministic decisions without an LLM, tool, or order dependency."""
    candidates = await repository.pending_candidates()
    scope_tickers = await repository.scope_tickers(as_of)
    accepted = 0
    rejected = 0
    for candidate in candidates:
        decision = route_candidate(candidate, scope_tickers)
        recorded = await repository.record(decision, candidate.ticker)
        if not recorded:
            continue
        match decision:
            case AcceptedRoute():
                accepted += 1
            case RejectedRoute():
                rejected += 1
            case unreachable:
                assert_never(unreachable)
    return RoutingRun(accepted=accepted, rejected=rejected)
