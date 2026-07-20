"""Role 09 reads the account it is actually sizing for.

Position size used to come from an app-wide env cap, so every account — a
$150,000 one and a $5,000 one — would have ordered the same notional. The
limits are per account, so the state feeding them must be per account too.
"""

import os
from decimal import Decimal

import pytest

from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.domain_records import AccountWrite

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")


async def _domain() -> PostgresDomainRepository:
    assert DATABASE_URL is not None
    domain = PostgresDomainRepository(DATABASE_URL)
    await domain.initialize()
    return domain


async def _account(broker_account_id: str, equity: str, inv_type: str) -> int:
    domain = await _domain()
    return await domain.save_account(
        AccountWrite(
            broker_account_id=broker_account_id,
            cash=Decimal(equity),
            equity=Decimal(equity),
            buying_power=Decimal(equity),
            inv_type=inv_type,
        )
    )


@pytest.mark.anyio
async def test_state_reports_the_accounts_own_capital() -> None:
    account_id = await _account("RISK-STATE-01", "150000.00", "aggressive")
    domain = await _domain()

    state = await domain.account_risk_state(account_id)

    assert state.equity == Decimal("150000.00")
    assert state.cash == Decimal("150000.00")
    assert state.inv_type == "aggressive"


@pytest.mark.anyio
async def test_a_fresh_account_holds_no_positions() -> None:
    account_id = await _account("RISK-STATE-02", "5000.00", "conservative")
    domain = await _domain()

    state = await domain.account_risk_state(account_id)

    assert state.open_position_count == 0
    assert state.inv_type == "conservative"


@pytest.mark.anyio
async def test_two_accounts_report_independent_capital() -> None:
    big = await _account("RISK-STATE-03", "150000.00", "aggressive")
    small = await _account("RISK-STATE-04", "5000.00", "aggressive")
    domain = await _domain()

    assert (await domain.account_risk_state(big)).equity == Decimal("150000.00")
    assert (await domain.account_risk_state(small)).equity == Decimal("5000.00")


@pytest.mark.anyio
async def test_an_unknown_account_has_no_state() -> None:
    domain = await _domain()

    assert await domain.account_risk_state(9_999_999) is None
