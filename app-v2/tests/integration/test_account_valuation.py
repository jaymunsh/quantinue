"""Phase 2 (D8): account equity is cash plus holdings marked to the last bar."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.db.domain_records import DailyBarWrite
from quantinue.db.postgres import PostgresRunStore

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)

_DAY = date(2026, 7, 8)
_INSERT_SIGNAL = """INSERT INTO tb_strategist_signals(
    trade_date,ticker,cycle_ts,inv_type,side,conviction,
    signal_consensus,summary,evidence,sizing_hint,decision_close,current_price,
    day_high,day_low,close_prev,volume,turnover,high_52w,low_52w)
VALUES (:day,:ticker,:cycle,'aggressive','buy',0.800,
    2,'fixture','[]','{}',100,100,100,100,100,0,0,100,100)
RETURNING id"""


async def _seed_holding(database_url: str, suffix: str) -> tuple[int, str]:
    """One account with 100,000 cash that bought 10 shares at 100 (so 99,000 left)."""
    engine = create_async_engine(database_url)
    ticker = f"VAL{suffix}"
    async with engine.begin() as connection:
        account_id = await connection.scalar(
            text(
                """INSERT INTO tb_account(
                    broker_account_id,currency,cash,equity,buying_power,is_paper,
                    status,inv_type)
                VALUES (:bid,'USD',99000,100000,99000,TRUE,'active','aggressive')
                RETURNING id"""
            ),
            {"bid": f"TEST-VALUATION-{suffix}"},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Valuation',1) ON CONFLICT DO NOTHING"""
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
            text(_INSERT_SIGNAL),
            {"day": _DAY, "ticker": ticker, "cycle": datetime(2026, 7, 8, 14, tzinfo=UTC)},
        )
        order_id = await connection.scalar(
            text(
                """INSERT INTO tb_order(
                    signal_id,account_id,ticker,quantity,entry_price,stop_price,
                    take_profit_price,status,idempotency_key,order_type)
                VALUES (:signal,:account,:ticker,10,100,85,120,'filled',:key,'bracket')
                RETURNING id"""
            ),
            {
                "signal": signal_id,
                "account": account_id,
                "ticker": ticker,
                "key": f"val-{suffix}-buy",
            },
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_fill(
                    order_id,side,quantity,price,filled_at,broker_fill_id)
                VALUES (:order,'buy',10,100,:at,:key)"""
            ),
            {
                "order": order_id,
                "at": datetime(2026, 7, 8, 14, tzinfo=UTC),
                "key": f"val-{suffix}-buy-fill",
            },
        )
    await engine.dispose()
    return int(account_id or 0), ticker


@pytest.mark.anyio
async def test_equity_follows_the_market_instead_of_staying_frozen() -> None:
    """ghost 감사 §2: equity가 최초 자본에 동결돼 미실현손익을 잴 수 없었다."""
    # Given: 10주를 100에 샀고 현재가는 120
    assert DATABASE_URL is not None
    account_id, ticker = await _seed_holding(DATABASE_URL, "a")
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    await store.domain.save_daily_bars(
        (
            DailyBarWrite(
                trade_date=_DAY,
                ticker=ticker,
                open=Decimal("100.00"),
                high=Decimal("125.00"),
                low=Decimal("99.00"),
                close=Decimal("120.00"),
                volume=1000,
                source="test",
            ),
        )
    )

    # When
    updated = await store.domain.revalue_accounts(_DAY)

    # Then: 현금 99,000 + 보유 10주 * 120 = 100,200
    assert account_id in updated
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        equity = await connection.scalar(
            text("SELECT equity FROM tb_account WHERE id = :aid"), {"aid": account_id}
        )
    await engine.dispose()
    assert Decimal(str(equity)) == Decimal("100200.00")
    await store.close()


@pytest.mark.anyio
async def test_a_holding_without_a_bar_keeps_its_cost_basis() -> None:
    """시세를 못 받은 종목을 0으로 평가하면 계좌가 하루아침에 파산한 것처럼 보인다."""
    # Given: 봉을 적재하지 않는다
    assert DATABASE_URL is not None
    account_id, _ = await _seed_holding(DATABASE_URL, "b")
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()

    # When
    _ = await store.domain.revalue_accounts(_DAY)

    # Then: 현금 99,000 + 보유 10주 * 진입가 100 = 100,000 (최초 자본과 같음)
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        equity = await connection.scalar(
            text("SELECT equity FROM tb_account WHERE id = :aid"), {"aid": account_id}
        )
    await engine.dispose()
    assert Decimal(str(equity)) == Decimal("100000.00")
    await store.close()


@pytest.mark.anyio
async def test_revaluation_is_repeatable_without_drift() -> None:
    """일 1회 잡이 두 번 돌아도 평가액이 누적되면 안 된다."""
    # Given
    assert DATABASE_URL is not None
    account_id, ticker = await _seed_holding(DATABASE_URL, "c")
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    await store.domain.save_daily_bars(
        (
            DailyBarWrite(
                trade_date=_DAY,
                ticker=ticker,
                open=Decimal("100.00"),
                high=Decimal("125.00"),
                low=Decimal("99.00"),
                close=Decimal("120.00"),
                volume=1000,
                source="test",
            ),
        )
    )

    # When
    _ = await store.domain.revalue_accounts(_DAY)
    _ = await store.domain.revalue_accounts(_DAY)

    # Then
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        equity = await connection.scalar(
            text("SELECT equity FROM tb_account WHERE id = :aid"), {"aid": account_id}
        )
    await engine.dispose()
    assert Decimal(str(equity)) == Decimal("100200.00")
    await store.close()
