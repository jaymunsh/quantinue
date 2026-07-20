"""Phase 5: the reads that let the control room answer "what did today do?".

The job ledger was write-only from the web layer's point of view — the runner
wrote rows nobody could list. These reads are the dashboard's whole evidence
base, so each one is pinned against real rows rather than a mock.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.db.postgres import PostgresRunStore

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)

_DAY = date(2026, 7, 20)
_MIDNIGHT = datetime.combine(_DAY, time(), tzinfo=UTC)


async def _store() -> PostgresRunStore:
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    return store


async def _seed_job_run(
    job_name: str,
    *,
    slot_date: date = _DAY,
    status: str = "succeeded",
    detail: str | None = "fixture",
    started_at: datetime | None = None,
) -> None:
    """Write one job ledger row the way the job runner would."""
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    started = started_at or _MIDNIGHT
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_job_run(
                    job_name,slot_date,status,detail,started_at,finished_at)
                VALUES (:name,:slot,:status,:detail,:started,:finished)
                ON CONFLICT (job_name,slot_date) DO UPDATE
                SET status=EXCLUDED.status, detail=EXCLUDED.detail"""
            ),
            {
                "name": job_name,
                "slot": slot_date,
                "status": status,
                "detail": detail,
                "started": started,
                # running 슬롯은 finished_at이 NULL이어야 한다(스키마 CHECK).
                "finished": None if status == "running" else started + timedelta(minutes=1),
            },
        )
    await engine.dispose()


@pytest.mark.anyio
async def test_the_days_job_chain_comes_back_in_execution_order() -> None:
    """관제실은 등록 순서 = 실행 순서를 그대로 보여야 한다."""
    # Given
    store = await _store()
    await _seed_job_run("chain-universe", started_at=_MIDNIGHT)
    await _seed_job_run("chain-bars", started_at=_MIDNIGHT + timedelta(minutes=5))
    await _seed_job_run("chain-exits", started_at=_MIDNIGHT + timedelta(minutes=9))

    # When
    runs = await store.domain.job_runs(_DAY)

    # Then
    names = [run.job_name for run in runs if run.job_name.startswith("chain-")]
    assert names == ["chain-universe", "chain-bars", "chain-exits"]
    await store.close()


@pytest.mark.anyio
async def test_a_failed_job_keeps_its_detail_so_the_room_can_say_why() -> None:
    # Given
    store = await _store()
    await _seed_job_run("chain-failed", status="failed", detail="alpaca 400")

    # When
    runs = await store.domain.job_runs(_DAY)

    # Then
    failed = next(run for run in runs if run.job_name == "chain-failed")
    assert failed.status == "failed"
    assert failed.detail == "alpaca 400"
    assert failed.finished_at is not None
    await store.close()


@pytest.mark.anyio
async def test_a_running_job_has_no_finish_time() -> None:
    """도는 중인 잡을 끝난 것처럼 그리면 관제실이 거짓말을 한다."""
    # Given
    store = await _store()
    await _seed_job_run("chain-running", status="running", detail=None)

    # When
    runs = await store.domain.job_runs(_DAY)

    # Then
    running = next(run for run in runs if run.job_name == "chain-running")
    assert running.status == "running"
    assert running.finished_at is None
    await store.close()


@pytest.mark.anyio
async def test_the_latest_slot_is_the_day_the_room_opens_on() -> None:
    # Given
    store = await _store()
    await _seed_job_run("slot-old", slot_date=date(2026, 7, 1))
    await _seed_job_run("slot-new", slot_date=date(2026, 7, 22))

    # When
    latest = await store.domain.latest_job_slot()

    # Then
    assert latest == date(2026, 7, 22)
    await store.close()


@pytest.mark.anyio
async def test_an_empty_ledger_has_no_latest_slot() -> None:
    """잡이 한 번도 안 돈 설치에서 화면이 예외로 죽으면 안 된다."""
    # Given
    store = await _store()
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(text("DELETE FROM tb_job_run"))
    await engine.dispose()

    # When
    latest = await store.domain.latest_job_slot()

    # Then
    assert latest is None
    await store.close()


@pytest.mark.anyio
async def test_allocation_decisions_come_back_with_their_skip_reasons() -> None:
    """배분이 왜 안 샀는지가 관제실의 핵심 질문이다."""
    # Given
    store = await _store()
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_order_plan(
                    run_id,ticker,cycle_ts,trade_date,decision,skipped_reason,quantity,entry_price)
                VALUES ('room','PLANBUY',:cycle,:day,'planned',NULL,10,50),
                       ('room','PLANSKIP',:cycle,:day,'skipped','min_cash',0,NULL)
                ON CONFLICT DO NOTHING"""
            ),
            {"cycle": _MIDNIGHT, "day": _DAY},
        )
    await engine.dispose()

    # When
    plans = await store.domain.order_plans(_DAY)

    # Then
    by_ticker = {plan.ticker: plan for plan in plans}
    assert by_ticker["PLANBUY"].decision == "planned"
    assert by_ticker["PLANBUY"].quantity == 10
    assert by_ticker["PLANSKIP"].decision == "skipped"
    assert by_ticker["PLANSKIP"].skipped_reason == "min_cash"
    await store.close()


@pytest.mark.anyio
async def test_the_equity_curve_comes_back_oldest_first_per_account() -> None:
    # Given
    store = await _store()
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        account_id = await connection.scalar(
            text(
                """INSERT INTO tb_account(broker_account_id,cash,equity,buying_power,inv_type)
                VALUES ('curve-acct',100,100,100,'aggressive') RETURNING id"""
            )
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_account_equity_daily(account_id,trade_date,equity)
                VALUES (:acct,:first,1000),(:acct,:second,1200)
                ON CONFLICT DO NOTHING"""
            ),
            {"acct": account_id, "first": _DAY - timedelta(days=1), "second": _DAY},
        )
    await engine.dispose()

    # When
    points = await store.domain.account_equity_series(days=30)

    # Then
    mine = [point for point in points if point.account_id == account_id]
    assert [point.trade_date for point in mine] == [_DAY - timedelta(days=1), _DAY]
    assert mine[-1].equity == Decimal(1200)
    await store.close()


async def _seed_judgement(
    ticker: str,
    *,
    side: str = "buy",
    verdict: str | None = "pass",
    cycle_ts: datetime = _MIDNIGHT,
) -> None:
    """Write the analysis job's output: a signal, then optionally its verdict."""
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Control Room',1) ON CONFLICT DO NOTHING"""
            ),
            {"day": _DAY, "ticker": ticker},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_daily_pick(
                    trade_date,ticker,universe_as_of,bucket,rank,sector,score)
                VALUES (:day,:ticker,:day,'backfill',1,'test',1)
                ON CONFLICT DO NOTHING"""
            ),
            {"day": _DAY, "ticker": ticker},
        )
        signal_id = await connection.scalar(
            text(
                """INSERT INTO tb_strategist_signals(
                    trade_date,ticker,cycle_ts,inv_type,side,conviction,
                    signal_consensus,summary,evidence,sizing_hint,decision_close,
                    current_price,day_high,day_low,close_prev,volume,turnover,
                    high_52w,low_52w)
                VALUES (:day,:ticker,:cycle,'aggressive',:side,0.800,
                    2,'room fixture','[]','{}',50,50,50,50,50,0,0,50,50)
                RETURNING id"""
            ),
            {"day": _DAY, "ticker": ticker, "cycle": cycle_ts, "side": side},
        )
        if verdict is not None:
            _ = await connection.execute(
                text(
                    """INSERT INTO tb_critic_verdict(
                        signal_id,ticker,decision,category,objection,confidence,
                        decided_layer,verdict_source)
                    VALUES (:signal,:ticker,:decision,'model_review','반박문',0.700,
                        'llm','fresh')"""
                ),
                {"signal": signal_id, "ticker": ticker, "decision": verdict},
            )
    await engine.dispose()


@pytest.mark.anyio
async def test_a_judgement_carries_its_rebuttal() -> None:
    # Given
    store = await _store()
    await _seed_judgement("JUDGED", verdict="reject")

    # When
    judgements = await store.domain.judgements(_DAY)

    # Then
    judged = next(item for item in judgements if item.ticker == "JUDGED")
    assert judged.side == "buy"
    assert judged.inv_type == "aggressive"
    assert judged.verdict_decision == "reject"
    assert judged.objection == "반박문"
    assert judged.verdict_confidence == Decimal("0.700")
    await store.close()


@pytest.mark.anyio
async def test_an_unjudged_signal_still_appears() -> None:
    """크리틱 전에 죽은 판단을 숨기면 관제실이 그 사고를 못 보여준다."""
    # Given
    store = await _store()
    await _seed_judgement("UNJUDGED", verdict=None)

    # When
    judgements = await store.domain.judgements(_DAY)

    # Then
    unjudged = next(item for item in judgements if item.ticker == "UNJUDGED")
    assert unjudged.verdict_decision is None
    assert unjudged.objection is None
    await store.close()


@pytest.mark.anyio
async def test_a_judgement_from_another_cycle_is_not_counted() -> None:
    """관제실이 배분보다 많이 세면 원장과 화면 중 무엇을 믿을지 알 수 없다.

    실 dev DB에서 잡힌 결함이다: 구 러너의 장중 행과 마이크로초가 밀린 과거
    실험 행이 섞여, 잡 원장이 "22건 분석"이라고 적은 날 화면이 28건을 셌다.
    자정 필터는 프로덕션 경로(approved_buy_candidates)와 같은 계약이다.
    """
    # Given
    store = await _store()
    await _seed_judgement("OFFCYCLE", cycle_ts=_MIDNIGHT + timedelta(microseconds=3))

    # When
    judged = await store.domain.judgements(_DAY)

    # Then
    assert all(item.ticker != "OFFCYCLE" for item in judged)
    await store.close()
