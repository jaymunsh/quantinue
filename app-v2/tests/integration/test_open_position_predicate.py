"""Phase 1a: an open position is a filled buy that nothing has closed yet."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.db.postgres import PostgresRunStore

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)


async def _seed_closed_round_trip(database_url: str, ticker: str) -> int:
    """Create one account whose only position was bought and then fully closed.

    Returns the account id. Signals are inserted directly rather than through
    stage 08 so the fixture states exactly what it means: a buy leg, a sell leg,
    and a close order that points at the buy.
    """
    engine = create_async_engine(database_url)
    cycle = datetime(2041, 5, 6, 14, tzinfo=UTC)
    async with engine.begin() as connection:
        account_id = await connection.scalar(
            text(
                """INSERT INTO tb_account(
                    broker_account_id,currency,cash,equity,buying_power,is_paper,
                    status,inv_type)
                VALUES (:bid,'USD',100000,100000,100000,TRUE,'active','aggressive')
                RETURNING id"""
            ),
            {"bid": f"TEST-OPENPOS-{ticker}"},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,:ticker,'Open Position',1) ON CONFLICT DO NOTHING"""
            ),
            {"day": cycle.date(), "ticker": ticker},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_daily_pick(
                    trade_date,ticker,universe_as_of,bucket,rank,sector,score)
                VALUES (:day,:ticker,:day,'backfill',1,'test',1)
                ON CONFLICT DO NOTHING"""
            ),
            {"day": cycle.date(), "ticker": ticker},
        )
        signals: dict[str, int] = {}
        for side in ("buy", "sell"):
            signals[side] = await connection.scalar(
                text(
                    """INSERT INTO tb_strategist_signals(
                        trade_date,ticker,cycle_ts,inv_type,side,conviction,
                        signal_consensus,summary,evidence,sizing_hint,
                        decision_close,current_price,day_high,day_low,close_prev,
                        volume,turnover,high_52w,low_52w)
                    VALUES (:day,:ticker,:cycle,'aggressive',:side,0.800,
                        2,'fixture','[]','{}',100,100,100,100,100,0,0,100,100)
                    RETURNING id"""
                ),
                {
                    "day": cycle.date(),
                    "ticker": ticker,
                    # cycle_ts는 side마다 달라야 한다 — UNIQUE(ticker,cycle_ts,inv_type)
                    "cycle": cycle if side == "buy" else datetime(2041, 5, 7, 14, tzinfo=UTC),
                    "side": side,
                },
            )
        buy_order_id = await connection.scalar(
            text(
                """INSERT INTO tb_order(
                    signal_id,account_id,ticker,quantity,entry_price,stop_price,
                    take_profit_price,status,idempotency_key,order_type)
                VALUES (:signal,:account,:ticker,2,100,85,120,'filled',
                    :key,'bracket')
                RETURNING id"""
            ),
            {
                "signal": signals["buy"],
                "account": account_id,
                "ticker": ticker,
                "key": f"openpos-{ticker}-buy",
            },
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_order(
                    signal_id,account_id,ticker,quantity,entry_price,status,
                    idempotency_key,order_type,closes_order_id)
                VALUES (:signal,:account,:ticker,2,130,'filled',
                    :key,'close',:closes)"""
            ),
            {
                "signal": signals["sell"],
                "account": account_id,
                "ticker": ticker,
                "key": f"openpos-{ticker}-close",
                "closes": buy_order_id,
            },
        )
    await engine.dispose()
    return int(account_id or 0)


@pytest.mark.anyio
async def test_a_closed_round_trip_leaves_no_open_position() -> None:
    """Buying then fully closing must return the account to zero positions."""
    # Given
    assert DATABASE_URL is not None
    account_id = await _seed_closed_round_trip(DATABASE_URL, "OPENA")
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()

    # When
    state = await store.domain.account_risk_state(account_id)

    # Then: the buy is closed, and the close row must not count as a holding
    assert state is not None
    assert state.open_position_count == 0
    await store.close()


@pytest.mark.anyio
async def test_active_accounts_agrees_with_single_account_risk_state() -> None:
    """Both readers must derive holdings the same way or limits disagree."""
    # Given
    assert DATABASE_URL is not None
    account_id = await _seed_closed_round_trip(DATABASE_URL, "OPENB")
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()

    # When
    single = await store.domain.account_risk_state(account_id)
    listed = {
        state.account_id: state for state in await store.domain.active_accounts()
    }

    # Then
    assert single is not None
    assert listed[account_id].open_position_count == single.open_position_count
    assert listed[account_id].open_position_count == 0
    await store.close()


@pytest.mark.anyio
async def test_an_unclosed_filled_buy_still_counts_as_one_position() -> None:
    """The fix must not swing the other way and hide genuine holdings."""
    # Given: same fixture, then a second ticker bought and left open
    assert DATABASE_URL is not None
    account_id = await _seed_closed_round_trip(DATABASE_URL, "OPENC")
    engine = create_async_engine(DATABASE_URL)
    cycle = datetime(2041, 5, 8, 14, tzinfo=UTC)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """INSERT INTO tb_universe(as_of_date,ticker,company_name,market_cap)
                VALUES (:day,'OPENHELD','Still Held',1) ON CONFLICT DO NOTHING"""
            ),
            {"day": cycle.date()},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_daily_pick(
                    trade_date,ticker,universe_as_of,bucket,rank,sector,score)
                VALUES (:day,'OPENHELD',:day,'backfill',1,'test',1)
                ON CONFLICT DO NOTHING"""
            ),
            {"day": cycle.date()},
        )
        signal_id = await connection.scalar(
            text(
                """INSERT INTO tb_strategist_signals(
                    trade_date,ticker,cycle_ts,inv_type,side,conviction,
                    signal_consensus,summary,evidence,sizing_hint,
                    decision_close,current_price,day_high,day_low,close_prev,
                    volume,turnover,high_52w,low_52w)
                VALUES (:day,'OPENHELD',:cycle,'aggressive','buy',0.800,
                    2,'fixture','[]','{}',100,100,100,100,100,0,0,100,100)
                RETURNING id"""
            ),
            {"day": cycle.date(), "cycle": cycle},
        )
        _ = await connection.execute(
            text(
                """INSERT INTO tb_order(
                    signal_id,account_id,ticker,quantity,entry_price,stop_price,
                    take_profit_price,status,idempotency_key,order_type)
                VALUES (:signal,:account,'OPENHELD',1,100,85,120,'filled',
                    'openpos-held','bracket')"""
            ),
            {"signal": signal_id, "account": account_id},
        )
    await engine.dispose()
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()

    # When
    state = await store.domain.account_risk_state(account_id)

    # Then: closed round trip drops out, the open buy remains
    assert state is not None
    assert state.open_position_count == 1
    await store.close()
