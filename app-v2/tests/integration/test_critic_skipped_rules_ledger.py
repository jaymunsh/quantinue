"""The skipped-rule list has to survive into the column the UI reads.

컬럼(schema.sql:119)·계약 필드·화면("건너뛴 규칙")이 다 있는데 쓰는 코드가
없어서 화면이 늘 "없음"이었다 — 유령 감사에서 실재가 확인된 항목이다.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.db.domain_records import CriticVerdictWrite, StrategistSignalWrite
from quantinue.db.postgres import PostgresRunStore

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)

_DAY = date(2026, 7, 15)
_TICKER = "SKIPRULE"


@pytest.mark.anyio
async def test_the_skipped_rules_land_in_the_column_the_screen_reads() -> None:
    # Given
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Skip Rule',1) ON CONFLICT DO NOTHING"""
            ),
            {"day": _DAY, "ticker": _TICKER},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_daily_pick(
                    trade_date,ticker,universe_as_of,bucket,rank,sector,score)
                VALUES (:day,:ticker,:day,'backfill',1,'test',1)
                ON CONFLICT DO NOTHING"""
            ),
            {"day": _DAY, "ticker": _TICKER},
        )
    signal_id = await store.domain.save_signal(
        StrategistSignalWrite(
            run_id="skiprule",
            trade_date=_DAY,
            ticker=_TICKER,
            cycle_ts=datetime(2026, 7, 15, 14, tzinfo=UTC),
            side="sell",
            conviction=Decimal("0.300"),
            summary="fixture",
            decision_close=Decimal(100),
            evidence=(),
            inv_type="aggressive",
        )
    )

    # When
    _ = await store.domain.save_verdict(
        CriticVerdictWrite(
            signal_id=signal_id,
            ticker=_TICKER,
            decision="reject",
            category="model_review",
            objection="fixture",
            confidence=Decimal("0.400"),
            decided_layer="llm",
            skipped_rules=("macro_riskoff", "fake_consensus", "evidence_freshness"),
        )
    )

    # Then
    async with engine.begin() as connection:
        stored = await connection.scalar(
            text("SELECT skipped_rules FROM tb_critic_verdict WHERE signal_id = :id"),
            {"id": signal_id},
        )
    assert stored == ["macro_riskoff", "fake_consensus", "evidence_freshness"]
    await engine.dispose()
    await store.close()
