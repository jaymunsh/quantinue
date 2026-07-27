"""Demo seed: the S1 opening ledger, written twice, must not grow."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.demo.seed import (
    DemoListing,
    DemoSeedSpec,
    DemoUser,
    HeldPosition,
    seed_demo_ledger,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DATABASE_URL = os.getenv("QUANTINUE_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="disposable PostgreSQL URL not provided"
)

# 다른 통합군과 거래일을 겹치지 않게 별도 날을 쓴다 — 후보 풀이 trade_date
# 단위라 날을 공유하면 서로의 원장을 오염시킨다(allocation 테스트의 전례).
_DEMO_DAY = date(2026, 7, 31)
_CYCLE_TS = datetime(2026, 7, 31, 15, 0, tzinfo=UTC)

_SPEC = DemoSeedSpec(
    trade_date=_DEMO_DAY,
    cycle_ts=_CYCLE_TS,
    broker_account_id="DEMO-FILM-01",
    opening_cash=Decimal("100000.00"),
    inv_type="aggressive",
    held=(
        HeldPosition(
            listing=DemoListing(ticker="DEFCO", company="Defense Co", sector="Tech"),
            quantity=10,
            entry=Decimal("150.00"),
            stop=Decimal("139.50"),
            take=Decimal("172.50"),
        ),
        HeldPosition(
            listing=DemoListing(ticker="BADCO", company="Bad News Co", sector="Tech"),
            quantity=20,
            entry=Decimal("80.00"),
            stop=Decimal("72.00"),
            take=Decimal("96.00"),
        ),
    ),
    candidates=(DemoListing(ticker="GOODCO", company="Good News Co", sector="Tech"),),
    users=(
        DemoUser(
            login_id="demo-owner",
            display_name="데모 사용자",
            role="user",
            password_hash="argon2-hash-placeholder",
            owns_account=True,
        ),
    ),
)


@pytest.fixture(autouse=True)
async def _isolate_demo_rows() -> AsyncIterator[None]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """
                TRUNCATE
                  tb_order_plan, tb_fill, tb_order, tb_critic_verdict,
                  tb_strategist_signals, tb_account_equity_daily, tb_account,
                  tb_user, tb_daily_bar, tb_daily_pick, tb_universe
                RESTART IDENTITY CASCADE
                """
            )
        )
    try:
        yield
    finally:
        await engine.dispose()


async def _counts() -> dict[str, int]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM tb_order) AS orders,
                      (SELECT count(*) FROM tb_fill) AS fills,
                      (SELECT count(*) FROM tb_daily_pick) AS picks,
                      (SELECT count(*) FROM tb_account) AS accounts,
                      (SELECT count(*) FROM tb_user) AS users,
                      (SELECT count(*) FROM tb_account_equity_daily) AS equity_days
                    """
                )
            )
            row = rows.mappings().one()
            return dict(row)
    finally:
        await engine.dispose()


class TestSeedOpeningState:
    @pytest.mark.anyio
    async def test_seed_books_positions_orders_and_scope(self) -> None:
        assert DATABASE_URL is not None
        report = await seed_demo_ledger(DATABASE_URL, _SPEC)
        counts = await _counts()
        assert report.seeded_positions == 2
        assert len(report.signal_ids) == 2
        assert counts["orders"] == 2
        assert counts["fills"] == 2
        assert counts["picks"] == 3
        assert counts["accounts"] == 1
        assert counts["users"] == 1
        assert counts["equity_days"] == 1

    @pytest.mark.anyio
    async def test_reseeding_is_idempotent(self) -> None:
        assert DATABASE_URL is not None
        first = await seed_demo_ledger(DATABASE_URL, _SPEC)
        before = await _counts()
        second = await seed_demo_ledger(DATABASE_URL, _SPEC)
        after = await _counts()
        assert before == after
        assert first.signal_ids == second.signal_ids
        assert first.account_id == second.account_id

    @pytest.mark.anyio
    async def test_seeded_brackets_are_visible_to_the_watch_domain(self) -> None:
        assert DATABASE_URL is not None
        _ = await seed_demo_ledger(DATABASE_URL, _SPEC)
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        """
                        SELECT ticker, stop_price, take_profit_price, status
                        FROM tb_order ORDER BY ticker
                        """
                    )
                )
                orders = rows.mappings().all()
        finally:
            await engine.dispose()
        assert [order["ticker"] for order in orders] == ["BADCO", "DEFCO"]
        assert all(order["status"] == "filled" for order in orders)
        assert all(
            order["stop_price"] is not None and order["take_profit_price"] is not None
            for order in orders
        )
