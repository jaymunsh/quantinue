"""Typed reflected-table query helpers."""

from pydantic import TypeAdapter
from pydantic_core import to_json
from sqlalchemy import Table, and_, desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from quantinue.core.contracts import PipelineContext, PipelineRequest, PipelineRun, RunId
from quantinue.db.active_snapshot import ActivePipelineSnapshot, active_pipeline_snapshot
from quantinue.db.codec import CONTEXT_ADAPTER, AttemptRow
from quantinue.db.contracts import DailyOrderReservation, PersistedAttempt

_STRING_ADAPTER = TypeAdapter(str)


async def run_id_for(connection: AsyncConnection, runs: Table, key: str) -> str:
    """Resolve a deterministic key to its textual run identity."""
    value = await connection.scalar(select(runs.c.run_id).where(runs.c.idempotency_key == key))
    return _STRING_ADAPTER.validate_python(value)


async def failed_run_is_resumable(
    connection: AsyncConnection, runs: Table, attempts: Table, key: str
) -> bool:
    """Return whether the latest failed attempt has an explicitly transient code."""
    run_id = await run_id_for(connection, runs, key)
    last_code = await connection.scalar(
        select(attempts.c.error_code)
        .where(attempts.c.run_id == run_id)
        .order_by(desc(attempts.c.attempt_id))
        .limit(1)
    )
    return last_code in {
        "ROLE_TIMEOUT",
        "TRANSIENT_FAILURE",
        "TRANSIENT_HTTP_FAILURE",
        "TRANSPORT_FAILURE",
        "CONNECTION_FAILURE",
        "PERSISTENCE_UNAVAILABLE",
    }


async def resume_context(
    connection: AsyncConnection,
    runs: Table,
    checkpoints: Table,
    key: str,
    request: PipelineRequest,
) -> PipelineContext:
    """Restore the latest internal checkpoint, never a terminal run projection."""
    run_id = await run_id_for(connection, runs, key)
    payload = await connection.scalar(
        select(checkpoints.c.payload)
        .where(checkpoints.c.run_id == run_id)
        .order_by(desc(checkpoints.c.checkpoint_id))
        .limit(1)
    )
    if payload is None:
        return PipelineContext(request=request, run_id=RunId(run_id))
    return CONTEXT_ADAPTER.validate_json(to_json(payload))


async def close_stale_attempts(connection: AsyncConnection, attempts: Table, run_id: str) -> None:
    """Finalize attempts abandoned by a prior claim owner."""
    _ = await connection.execute(
        attempts.update()
        .where(attempts.c.run_id == run_id, attempts.c.status == "running")
        .values(
            status="failed",
            finished_at=func.now(),
            error_code="ABANDONED_ATTEMPT",
            error_message="prior owner exited before attempt finalization",
        )
    )


async def terminal_run_by_key(engine: AsyncEngine, runs: Table, key: str) -> PipelineRun | None:
    """Read a published terminal run, excluding active state."""
    async with engine.connect() as connection:
        row = (
            (await connection.execute(select(runs).where(runs.c.idempotency_key == key)))
            .mappings()
            .one_or_none()
        )
    if row is None or row["status"] not in {"completed", "failed"}:
        return None
    return PipelineRun.model_validate_json(to_json(row["payload"]))


async def recent_terminal_runs(
    engine: AsyncEngine, runs: Table, limit: int
) -> tuple[PipelineRun, ...]:
    """Read recent terminal runs in reverse cycle order."""
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(runs)
                .where(runs.c.status.in_(("completed", "failed")))
                .order_by(runs.c.cycle_ts.desc())
                .limit(limit)
            )
        ).mappings()
    return tuple(PipelineRun.model_validate_json(to_json(row["payload"])) for row in rows)


async def active_run_snapshots(
    engine: AsyncEngine, runs: Table, attempts: Table, limit: int
) -> tuple[ActivePipelineSnapshot, ...]:
    """Read in-progress checkpoint contexts with redacted attempts."""
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(runs)
                .where(runs.c.status == "running")
                .order_by(runs.c.cycle_ts.desc())
                .limit(limit)
            )
        ).mappings()
    snapshots: list[ActivePipelineSnapshot] = []
    for row in rows:
        context = CONTEXT_ADAPTER.validate_json(to_json(row["payload"]))
        run_attempts = await persisted_attempts(engine, attempts, context.run_id)
        snapshots.append(active_pipeline_snapshot(context, run_attempts))
    return tuple(snapshots)


async def reserve_daily_order(
    connection: AsyncConnection,
    orders: Table,
    signals: Table,
    request: DailyOrderReservation,
) -> bool:
    """Serialize account/day quota checks and canonical planned-order insertion."""
    lock_identity = f"daily-order:{request.account_id}:{request.trade_date.isoformat()}"
    _ = await connection.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(lock_identity, 0)))
    )
    existing = await connection.scalar(
        select(orders.c.id).where(orders.c.idempotency_key == request.idempotency_key)
    )
    if existing is not None:
        return True
    count = await connection.scalar(
        select(func.count())
        .select_from(orders.join(signals, orders.c.signal_id == signals.c.id))
        .where(
            and_(
                orders.c.account_id == request.account_id,
                signals.c.trade_date == request.trade_date,
            )
        )
    )
    if int(count or 0) >= request.cap:
        return False
    _ = await connection.execute(
        insert(orders).values(
            signal_id=request.signal_id,
            account_id=request.account_id,
            ticker=request.ticker,
            quantity=request.quantity,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            take_profit_price=request.take_profit_price,
            status="planned",
            idempotency_key=request.idempotency_key,
        )
    )
    return True


async def persisted_attempts(
    engine: AsyncEngine, attempts: Table, run_id: RunId
) -> tuple[PersistedAttempt, ...]:
    """Read durable attempts in insertion order."""
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(attempts)
                .where(attempts.c.run_id == str(run_id))
                .order_by(attempts.c.attempt_id)
            )
        ).mappings()
    parsed = (AttemptRow.model_validate(dict(row)) for row in rows)
    return tuple(
        PersistedAttempt(
            component=row.component,
            attempt_no=row.attempt_no,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            error_code=row.error_code,
            error_message=row.error_message,
        )
        for row in parsed
    )
