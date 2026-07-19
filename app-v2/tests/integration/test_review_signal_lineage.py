"""Phase 5: T+5 review must reach judgements the jobs made, not just the runner's.

`get_signal` inner-joined `pipeline_runs`, a table only the old 11-stage runner
ever wrote. Every job-produced judgement dropped out of that join silently, so
the review API could not score anything the new pipeline decided — verified on
the dev ledger: 91 job signals, 0 matches.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.db.reviews import PostgresReviewRepository

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)

_DAY = date(2026, 7, 20)
_MIDNIGHT = datetime.combine(_DAY, time(), tzinfo=UTC)


async def _seed_job_signal(ticker: str, *, inv_type: str = "aggressive") -> int:
    """Write a judgement the way the analysis job does — with no pipeline_runs row."""
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Review Lineage',1) ON CONFLICT DO NOTHING"""
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
                VALUES (:day,:ticker,:cycle,:inv_type,'buy',0.800,
                    2,'lineage fixture','[]','{}',50,50,50,50,50,0,0,50,50)
                RETURNING id"""
            ),
            {"day": _DAY, "ticker": ticker, "cycle": _MIDNIGHT, "inv_type": inv_type},
        )
    await engine.dispose()
    assert signal_id is not None
    return int(signal_id)


@pytest.mark.anyio
async def test_a_job_made_judgement_is_reviewable_without_a_runner_row() -> None:
    """잡 판단에 러너 행이 없다는 이유로 채점 대상에서 빠지면 안 된다."""
    # Given
    assert DATABASE_URL is not None
    signal_id = await _seed_job_signal("LINEAGE")
    repository = PostgresReviewRepository(DATABASE_URL)
    await repository.initialize()

    # When
    signal = await repository.get_signal(signal_id)

    # Then
    assert signal is not None
    assert signal.ticker == "LINEAGE"
    # 체결이 없는 매수 제안은 판단 시점 종가를 기준가로 삼는다 — 사지 않은
    # 제안이야말로 "샀으면 어땠나"를 물어야 하는 대상이다.
    assert signal.base_price == Decimal(50)
    await repository.close()


@pytest.mark.anyio
async def test_the_restored_run_id_matches_the_analysis_job_formula() -> None:
    """계보 문자열을 지어내면 리뷰 증거가 원래 실행과 안 맞물린다."""
    # Given
    assert DATABASE_URL is not None
    signal_id = await _seed_job_signal("FORMULA", inv_type="conservative")
    repository = PostgresReviewRepository(DATABASE_URL)
    await repository.initialize()

    # When
    signal = await repository.get_signal(signal_id)

    # Then
    assert signal is not None
    assert signal.run_id == "analysis:2026-07-20:conservative"
    await repository.close()
