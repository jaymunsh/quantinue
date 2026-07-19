"""Provisioning is safe to re-run against a ledger that already has money."""

import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.postgres import PostgresRunStore
from quantinue.db.provisioning import DEMO_ACCOUNTS, account_writes

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")


async def _store() -> PostgresRunStore:
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    return store


async def _provision() -> None:
    assert DATABASE_URL is not None
    domain = PostgresDomainRepository(DATABASE_URL)
    await domain.initialize()
    for write in account_writes():
        _ = await domain.save_account(write)


@pytest.mark.anyio
async def test_the_whole_roster_lands_with_its_investment_type() -> None:
    await _provision()
    store = await _store()

    async with store.engine.begin() as connection:
        rows = (
            await connection.execute(
                text("SELECT broker_account_id, inv_type, equity FROM tb_account")
            )
        ).all()

    found = {row[0]: (row[1], row[2]) for row in rows}
    for spec in DEMO_ACCOUNTS:
        assert spec.broker_account_id in found
        inv_type, equity = found[spec.broker_account_id]
        assert inv_type == spec.inv_type
        assert Decimal(str(equity)) == spec.equity


@pytest.mark.anyio
async def test_rerunning_never_resets_a_balance_that_has_traded() -> None:
    # Given: a provisioned account that has since spent some cash
    await _provision()
    store = await _store()
    async with store.engine.begin() as connection:
        _ = await connection.execute(
            text(
                "UPDATE tb_account SET cash = :cash "
                "WHERE broker_account_id = 'DEMO-AGGRESSIVE-01'"
            ),
            {"cash": Decimal("12345.67")},
        )

    # When: the script is run again
    await _provision()

    # Then: the traded balance survives
    async with store.engine.begin() as connection:
        cash = await connection.scalar(
            text("SELECT cash FROM tb_account WHERE broker_account_id = 'DEMO-AGGRESSIVE-01'")
        )
    assert Decimal(str(cash)) == Decimal("12345.67")


@pytest.mark.anyio
async def test_test_accounts_are_distinguishable_in_sql() -> None:
    await _provision()
    store = await _store()

    async with store.engine.begin() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM tb_account WHERE broker_account_id LIKE 'TEST-%'")
        )

    assert count == 2
