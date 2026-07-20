"""A close order is a real order, not a buy row with pretend numbers.

tb_order was bracket-buy only: `order_type` accepted just 'bracket', stop and
take-profit were NOT NULL, and `stop < entry < take_profit` cannot hold for an
exit. Filling those columns with dummy values to make a sell fit would repeat
the mistake this project keeps paying for — so the columns stay empty and the
bracket constraint becomes conditional.
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from quantinue.db.domain import PostgresDomainRepository

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")


async def _domain() -> PostgresDomainRepository:
    assert DATABASE_URL is not None
    domain = PostgresDomainRepository(DATABASE_URL)
    await domain.initialize()
    return domain


async def _buy_order(suffix: str) -> tuple[int, int, int]:
    """Create an account, a sell-able signal, and a filled bracket buy."""
    domain = await _domain()
    async with domain.engine.begin() as connection:
        account_id = await connection.scalar(
            text(
                "INSERT INTO tb_account (broker_account_id, cash, equity, buying_power)"
                " VALUES (:bid, 100000, 100000, 100000) RETURNING id"
            ),
            {"bid": f"CLOSE-{suffix}"},
        )
        _ = await connection.execute(
            text(
                "INSERT INTO tb_universe (as_of_date, ticker, company_name, market_cap)"
                " VALUES (CURRENT_DATE, 'NVDA', 'NVIDIA', 1)"
                " ON CONFLICT DO NOTHING"
            )
        )
        _ = await connection.execute(
            text(
                "INSERT INTO tb_daily_pick (trade_date, ticker, universe_as_of, bucket,"
                " rank, sector, score) VALUES (CURRENT_DATE, 'NVDA', CURRENT_DATE,"
                " 'trend_leader', 1, 'tech', 0.9) ON CONFLICT DO NOTHING"
            )
        )
        signal_id = await connection.scalar(
            text(
                "INSERT INTO tb_strategist_signals"
                " (trade_date, ticker, cycle_ts, inv_type, side, conviction,"
                "  signal_consensus, summary, evidence, sizing_hint, decision_close, current_price,"
                "  day_high, day_low, close_prev, volume, turnover, high_52w, low_52w)"
                " VALUES (CURRENT_DATE, 'NVDA', now(), 'aggressive', 'buy', 0.8,"
                "  2, 's', to_jsonb(ARRAY['e']), '{}'::jsonb, 100, 100, 100, 100,"
                "  100, 0, 0, 100, 100)"
                " RETURNING id"
            )
        )
        order_id = await connection.scalar(
            text(
                "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                " entry_price, stop_price, take_profit_price, status, idempotency_key)"
                " VALUES (:sig, :acc, 'NVDA', 10, 100, 85, 120, 'filled', :key)"
                " RETURNING id"
            ),
            {"sig": signal_id, "acc": account_id, "key": f"buy-{suffix}"},
        )
    return int(account_id), int(signal_id), int(order_id)


async def _sell_signal() -> int:
    domain = await _domain()
    async with domain.engine.begin() as connection:
        return int(
            await connection.scalar(
                text(
                    "INSERT INTO tb_strategist_signals"
                    " (trade_date, ticker, cycle_ts, inv_type, side, conviction,"
                    "  signal_consensus, summary, evidence, sizing_hint,"
                    "  decision_close, current_price,"
                    "  day_high, day_low, close_prev, volume, turnover, high_52w, low_52w)"
                    " VALUES (CURRENT_DATE, 'NVDA', now() + interval '1 hour', 'aggressive',"
                    "  'sell', 0.8, 2, 'exit', to_jsonb(ARRAY['e']), '{}'::jsonb,"
                    "  110, 110, 110, 110, 110, 0, 0, 110, 110) RETURNING id"
                )
            )
        )


@pytest.mark.anyio
async def test_a_close_order_needs_no_stop_or_take_profit() -> None:
    account_id, _, buy_id = await _buy_order("ok")
    sell_signal = await _sell_signal()
    domain = await _domain()

    async with domain.engine.begin() as connection:
        close_id = await connection.scalar(
            text(
                "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                " entry_price, order_type, closes_order_id, status, idempotency_key)"
                " VALUES (:sig, :acc, 'NVDA', 10, 110, 'close', :buy, 'planned', :key)"
                " RETURNING id"
            ),
            {"sig": sell_signal, "acc": account_id, "buy": buy_id, "key": "close-ok"},
        )

    assert close_id is not None


@pytest.mark.anyio
async def test_a_close_order_must_say_which_buy_it_closes() -> None:
    # 실현손익은 매수와 매도의 짝에서 나온다. 짝이 없으면 계산할 수 없다.
    account_id, _, _ = await _buy_order("orphan")
    sell_signal = await _sell_signal()
    domain = await _domain()

    with pytest.raises(IntegrityError):
        async with domain.engine.begin() as connection:
            _ = await connection.execute(
                text(
                    "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                    " entry_price, order_type, status, idempotency_key)"
                    " VALUES (:sig, :acc, 'NVDA', 10, 110, 'close', 'planned', :key)"
                ),
                {"sig": sell_signal, "acc": account_id, "key": "close-orphan"},
            )


@pytest.mark.anyio
async def test_a_bracket_buy_still_requires_its_full_triple() -> None:
    # 조건부로 바꿨다고 매수 쪽 보호가 느슨해지면 안 된다.
    account_id, _, _ = await _buy_order("strict")
    sell_signal = await _sell_signal()
    domain = await _domain()

    with pytest.raises(IntegrityError):
        async with domain.engine.begin() as connection:
            _ = await connection.execute(
                text(
                    "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                    " entry_price, status, idempotency_key)"
                    " VALUES (:sig, :acc, 'NVDA', 10, 100, 'planned', :key)"
                ),
                {"sig": sell_signal, "acc": account_id, "key": "bracket-naked"},
            )


@pytest.mark.anyio
async def test_an_inverted_bracket_is_still_rejected() -> None:
    account_id, _, _ = await _buy_order("inverted")
    sell_signal = await _sell_signal()
    domain = await _domain()

    with pytest.raises(IntegrityError):
        async with domain.engine.begin() as connection:
            _ = await connection.execute(
                text(
                    "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                    " entry_price, stop_price, take_profit_price, status, idempotency_key)"
                    " VALUES (:sig, :acc, 'NVDA', 10, 100, 120, 85, 'planned', :key)"
                ),
                {"sig": sell_signal, "acc": account_id, "key": "bracket-inverted"},
            )


@pytest.mark.anyio
async def test_a_sell_fill_attaches_to_the_close_order() -> None:
    account_id, _, buy_id = await _buy_order("fill")
    sell_signal = await _sell_signal()
    domain = await _domain()

    async with domain.engine.begin() as connection:
        close_id = await connection.scalar(
            text(
                "INSERT INTO tb_order (signal_id, account_id, ticker, quantity,"
                " entry_price, order_type, closes_order_id, status, idempotency_key)"
                " VALUES (:sig, :acc, 'NVDA', 10, 110, 'close', :buy, 'filled', :key)"
                " RETURNING id"
            ),
            {"sig": sell_signal, "acc": account_id, "buy": buy_id, "key": "close-fill"},
        )
        _ = await connection.execute(
            text(
                "INSERT INTO tb_fill (order_id, side, quantity, price, filled_at,"
                " broker_fill_id) VALUES (:oid, 'sell', 10, 110, now(), :fid)"
            ),
            {"oid": close_id, "fid": "sell-fill-1"},
        )
        realized = await connection.scalar(
            text(
                "SELECT (c.entry_price - b.entry_price) * f.quantity"
                " FROM tb_order c"
                " JOIN tb_order b ON b.id = c.closes_order_id"
                " JOIN tb_fill f ON f.order_id = c.id"
                " WHERE c.id = :cid"
            ),
            {"cid": close_id},
        )

    # 매수 $100 → 매도 $110, 10주 = +$100
    assert Decimal(str(realized)) == Decimal(100)
