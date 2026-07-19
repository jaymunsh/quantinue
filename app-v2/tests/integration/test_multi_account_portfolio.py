"""Each account owns its own cash, holdings, and totals.

The simulated ledger read one hardcoded account and took its opening cash from
an app-wide env value, so five demo accounts of different sizes could not be
represented at all.
"""

import os
from decimal import Decimal

import pytest

from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.domain_records import AccountWrite
from quantinue.db.postgres import PostgresRunStore

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")


async def _account(broker_account_id: str, equity: str, inv_type: str) -> int:
    assert DATABASE_URL is not None
    domain = PostgresDomainRepository(DATABASE_URL)
    await domain.initialize()
    return await domain.save_account(
        AccountWrite(
            broker_account_id=broker_account_id,
            cash=Decimal(equity),
            equity=Decimal(equity),
            buying_power=Decimal(equity),
            inv_type=inv_type,
        )
    )


async def _store() -> PostgresRunStore:
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    return store


@pytest.mark.anyio
async def test_each_account_reports_its_own_opening_capital() -> None:
    await _account("PORT-BIG-01", "150000.00", "aggressive")
    await _account("PORT-SMALL-01", "5000.00", "conservative")
    store = await _store()

    big = await store.account_portfolio("PORT-BIG-01")
    small = await store.account_portfolio("PORT-SMALL-01")

    assert big is not None
    assert small is not None
    assert big.account.opening_cash == Decimal("150000.00")
    assert small.account.opening_cash == Decimal("5000.00")


@pytest.mark.anyio
async def test_opening_capital_no_longer_comes_from_an_app_wide_value() -> None:
    # 환경변수 하나로는 자본이 다른 계좌 5개를 표현할 수 없다.
    await _account("PORT-A-01", "100000.00", "aggressive")
    await _account("PORT-A-02", "5000.00", "aggressive")
    store = await _store()

    first = await store.account_portfolio("PORT-A-01")
    second = await store.account_portfolio("PORT-A-02")

    assert first is not None
    assert second is not None
    assert first.account.opening_cash != second.account.opening_cash


@pytest.mark.anyio
async def test_a_fresh_account_is_all_cash_and_holds_nothing() -> None:
    await _account("PORT-FRESH-01", "100000.00", "aggressive")
    store = await _store()

    snapshot = await store.account_portfolio("PORT-FRESH-01")

    assert snapshot is not None
    assert snapshot.account.current_cash == Decimal("100000.00")
    assert snapshot.account.equity == Decimal("100000.00")
    assert snapshot.positions == ()


@pytest.mark.anyio
async def test_every_active_account_is_enumerable() -> None:
    await _account("PORT-ENUM-01", "100000.00", "aggressive")
    await _account("PORT-ENUM-02", "5000.00", "conservative")
    store = await _store()

    portfolios = await store.account_portfolios()

    identities = {item.broker_account_id for item in portfolios}
    assert {"PORT-ENUM-01", "PORT-ENUM-02"} <= identities
    by_id = {item.broker_account_id: item for item in portfolios}
    assert by_id["PORT-ENUM-02"].inv_type == "conservative"
    assert by_id["PORT-ENUM-02"].snapshot.account.opening_cash == Decimal("5000.00")


@pytest.mark.anyio
async def test_an_unknown_account_has_no_portfolio() -> None:
    store = await _store()

    assert await store.account_portfolio("PORT-DOES-NOT-EXIST") is None
