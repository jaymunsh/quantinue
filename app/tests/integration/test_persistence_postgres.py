from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.broker.reservations import (
    CompletedClaim,
    InFlightClaim,
    OwnerClaim,
    ReservationClaim,
)
from quantinue.core.config import DatabaseMode, Settings
from quantinue.core.contracts import OrderResult, PipelineContext, PipelineRequest, PipelineRun
from quantinue.db.contracts import DailyOrderReservation
from quantinue.db.order_reservations import PostgresOrderReservations
from quantinue.db.store import PostgresRunStore
from quantinue.main import create_app
from quantinue.orchestration.pipeline import PipelineOrchestrator
from quantinue.orchestration.policy import load_pipeline_policy

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")
_INT_ADAPTER = TypeAdapter(int)


@pytest.mark.skipif(DATABASE_URL is None, reason="real PostgreSQL integration URL not configured")
@pytest.mark.parametrize("ticker", ["../NVDA", "NVDA\x00", "<B>", "삼성"])
def test_postgres_api_returns_422_before_persistence_for_untrusted_ticker(ticker: str) -> None:
    settings = Settings.model_validate(
        {"database_mode": DatabaseMode.POSTGRES, "database_url": DATABASE_URL}
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/runs", json={"ticker": ticker})

    assert response.status_code == 422


def _result(order_id: str) -> OrderResult:
    return OrderResult(
        order_id=order_id,
        client_order_id="pg-reservation",
        status="filled",
        quantity=1,
        filled_avg_price=100.0,
    )


class _CountingRole:
    component: ClassVar[str] = "01"
    name: ClassVar[str] = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: PipelineContext) -> PipelineContext:
        self.calls += 1
        await anyio.sleep(0.01)
        return context.add_stage(self.component, self.name, "done")


class _FirstRole:
    component: ClassVar[str] = "01"
    name: ClassVar[str] = "first"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: PipelineContext) -> PipelineContext:
        self.calls += 1
        return replace(context, last_price=100.0).add_stage(self.component, self.name, "done")


class _InterruptRole:
    component: ClassVar[str] = "02"
    name: ClassVar[str] = "interrupt"

    def __init__(self) -> None:
        self.interrupted = False

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not self.interrupted:
            self.interrupted = True
            raise KeyboardInterrupt
        assert context.last_price == 100.0
        return context.add_stage(self.component, self.name, "resumed")


class _FailingRole:
    component: ClassVar[str] = "01"
    name: ClassVar[str] = "failure"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: PipelineContext) -> PipelineContext:
        self.calls += 1
        if self.calls > 1:
            return context.add_stage(self.component, self.name, "resumed")
        message = "persisted fixture failure"
        raise TimeoutError(message)


@pytest.mark.anyio
@pytest.mark.skipif(DATABASE_URL is None, reason="disposable PostgreSQL URL not provided")
async def test_postgres_atomic_claim_and_process_recreation_resume() -> None:
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    role = _CountingRole()
    orchestrator = PipelineOrchestrator((role,), store)
    request = PipelineRequest(ticker="PGCON", cycle_ts=datetime.now(UTC))
    results: list[PipelineRun] = []

    async def run_once() -> None:
        results.append(await orchestrator.run(request))

    async with anyio.create_task_group() as group:
        _ = group.start_soon(run_once)
        _ = group.start_soon(run_once)
    assert role.calls == 1
    assert results[0].run_id == results[1].run_id
    await store.close()

    first = _FirstRole()
    interrupted = _InterruptRole()
    resume_request = PipelineRequest(
        ticker="PGRESUME",
        cycle_ts=datetime.now(UTC) + timedelta(seconds=1),
    )
    before_restart = PostgresRunStore(DATABASE_URL)
    await before_restart.initialize()
    with pytest.raises(KeyboardInterrupt):
        _ = await PipelineOrchestrator((first, interrupted), before_restart).run(resume_request)
    await before_restart.close()

    after_restart = PostgresRunStore(DATABASE_URL)
    await after_restart.initialize()
    resumed = await PipelineOrchestrator((first, interrupted), after_restart).run(resume_request)
    assert first.calls == 1
    assert [stage.component for stage in resumed.stages] == ["01", "02"]
    attempts = await after_restart.list_attempts(resumed.run_id)
    assert [(item.component, item.attempt_no, item.status) for item in attempts] == [
        ("01", 1, "completed"),
        ("02", 1, "failed"),
        ("02", 2, "completed"),
    ]

    failure_request = PipelineRequest(
        ticker="PGFAIL",
        cycle_ts=datetime.now(UTC) + timedelta(seconds=2),
    )
    failing_role = _FailingRole()
    resume_policy = load_pipeline_policy(Path("config/pipeline.yaml")).model_copy(
        update={"role_max_retries": 0}
    )
    with pytest.raises(TimeoutError, match="persisted fixture failure"):
        _ = await PipelineOrchestrator((failing_role,), after_restart, policy=resume_policy).run(
            failure_request
        )
    failed = next(run for run in await after_restart.list_recent(100) if run.ticker == "PGFAIL")
    failed_attempts = await after_restart.list_attempts(failed.run_id)
    assert failed_attempts[0].status == "timed_out"
    assert failed_attempts[0].error_code == "ROLE_TIMEOUT"
    failed_run_id = failed.run_id
    resumed_failure = await PipelineOrchestrator(
        (failing_role,), after_restart, policy=resume_policy
    ).run(failure_request)
    assert resumed_failure.run_id == failed_run_id
    assert resumed_failure.status.value == "completed"
    await after_restart.close()


@pytest.mark.anyio
@pytest.mark.skipif(DATABASE_URL is None, reason="disposable PostgreSQL URL not provided")
async def test_postgres_order_reservation_single_owner_and_aba_guard() -> None:
    assert DATABASE_URL is not None
    first = PostgresOrderReservations(DATABASE_URL, stale_after_seconds=60)
    second = PostgresOrderReservations(DATABASE_URL, stale_after_seconds=60)
    await first.initialize()
    await second.initialize()
    claims: list[ReservationClaim] = []
    reservation_id = f"pg-reservation-{uuid4().hex}"

    async def claim(adapter: PostgresOrderReservations) -> None:
        claims.append(await adapter.claim(reservation_id))

    async with anyio.create_task_group() as group:
        _ = group.start_soon(claim, first)
        _ = group.start_soon(claim, second)
    owners = [item for item in claims if isinstance(item, OwnerClaim)]
    assert len(owners) == 1
    assert sum(isinstance(item, InFlightClaim) for item in claims) == 1
    assert await first.complete(reservation_id, owners[0].owner_token, _result("winner"))
    cached = await second.claim(reservation_id)
    assert isinstance(cached, CompletedClaim)
    assert cached.result.order_id == "winner"
    await first.close()
    await second.close()

    stale = PostgresOrderReservations(DATABASE_URL, stale_after_seconds=0)
    await stale.initialize()
    aba_id = f"pg-aba-{uuid4().hex}"
    old = await stale.claim(aba_id)
    new = await stale.claim(aba_id)
    assert isinstance(old, OwnerClaim)
    assert isinstance(new, OwnerClaim)
    assert old.owner_token != new.owner_token
    assert await stale.complete(aba_id, new.owner_token, _result("new"))
    assert not await stale.complete(aba_id, old.owner_token, _result("old"))
    assert not await stale.release(aba_id, old.owner_token)
    await stale.close()


@pytest.mark.anyio
@pytest.mark.skipif(DATABASE_URL is None, reason="disposable PostgreSQL URL not provided")
async def test_postgres_daily_order_cap_is_cross_process_atomic() -> None:
    assert DATABASE_URL is not None
    ticker = f"C{uuid4().hex[:8]}".upper()
    trade_date = datetime.now(UTC).date()
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Cap Test',1)"""
            ),
            {"day": trade_date, "ticker": ticker},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_daily_pick(
                trade_date,ticker,universe_as_of,bucket,rank,sector,score
                ) VALUES (:day,:ticker,:day,'backfill',1,'test',1)"""
            ),
            {"day": trade_date, "ticker": ticker},
        )
        account_id_int = _INT_ADAPTER.validate_python(
            await connection.scalar(
                text(
                    """INSERT INTO tb_account(broker_account_id,cash,equity,buying_power)
                    VALUES (:broker,1000,1000,1000) RETURNING id"""
                ),
                {"broker": f"cap-{uuid4().hex}"},
            )
        )
        signal_ids: list[int] = []
        for offset in (1, 2):
            signal_id_int = _INT_ADAPTER.validate_python(
                await connection.scalar(
                    text(
                        """INSERT INTO tb_strategist_signals(
                        trade_date,ticker,cycle_ts,inv_type,side,conviction,signal_consensus,
                        summary,evidence,sizing_hint,decision_close,current_price,day_high,
                        day_low,close_prev,volume,turnover,high_52w,low_52w
                        ) VALUES (:day,:ticker,:cycle,'aggressive','buy',0.8,2,'cap','{}','{}',
                        100,100,101,99,99,1,100,120,80) RETURNING id"""
                    ),
                    {
                        "day": trade_date,
                        "ticker": ticker,
                        "cycle": datetime.now(UTC) + timedelta(seconds=offset),
                    },
                )
            )
            signal_ids.append(signal_id_int)
    first = PostgresRunStore(DATABASE_URL)
    second = PostgresRunStore(DATABASE_URL)
    await first.initialize()
    await second.initialize()
    outcomes: list[bool] = []

    async def reserve(store: PostgresRunStore, signal_id: int) -> None:
        outcomes.append(
            await store.reserve_daily_new_order(
                DailyOrderReservation(
                    account_id=account_id_int,
                    trade_date=trade_date,
                    signal_id=signal_id,
                    idempotency_key=f"q-a{account_id_int}-s{signal_id}",
                    ticker=ticker,
                    quantity=1,
                    entry_price=100,
                    stop_price=85,
                    take_profit_price=120,
                    cap=1,
                )
            )
        )

    async with anyio.create_task_group() as group:
        _ = group.start_soon(reserve, first, signal_ids[0])
        _ = group.start_soon(reserve, second, signal_ids[1])
    assert sorted(outcomes) == [False, True]
    await first.close()
    await second.close()
    await engine.dispose()
