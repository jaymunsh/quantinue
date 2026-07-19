"""E2E-5: the same signal sizes differently per account subscription.

The `conservative` profile was unreachable — `DEFAULT_PROFILE_NAME` was
hardcoded — so every account traded aggressively regardless of its declared
investment type. The account's `inv_type` now selects the profile.
"""

import os
from decimal import Decimal

import pytest

from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.domain_records import AccountRiskState, AccountWrite
from quantinue.orchestration.policy import ProfileConfig
from quantinue.roles.role_09_risk_portfolio.contracts import (
    RiskPortfolioInput,
    RiskPortfolioOutput,
    build_order_plan,
)

from .test_m4_guards_end_to_end import _EVIDENCE_FOR_PROFILE_TEST as EVIDENCE

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")

PROFILES = {
    "aggressive": ProfileConfig(),
    "conservative": ProfileConfig(
        buy_threshold=0.75, max_positions=5, max_weight=0.10, min_cash_ratio=0.30
    ),
}


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


async def _state(account_id: int) -> AccountRiskState:
    assert DATABASE_URL is not None
    domain = PostgresDomainRepository(DATABASE_URL)
    await domain.initialize()
    state = await domain.account_risk_state(account_id)
    assert state is not None
    return state


def _plan_for(state: AccountRiskState, price: float = 100.0) -> RiskPortfolioOutput:
    profile = PROFILES[state.inv_type or "aggressive"]
    request = RiskPortfolioInput(
        run_id="run-profile",
        execution_at=EVIDENCE.captured_at,
        evidence=(EVIDENCE,),
        signal_id=1,
        account_id=state.account_id,
        ticker="NVDA",
        cycle_ts=EVIDENCE.captured_at,
        critic_approved=True,
        current_price=price,
        equity=float(state.equity),
        cash=float(state.cash),
        open_position_count=state.open_position_count,
        daily_new_order_cap=5,
    )
    return build_order_plan(request, profile=profile)


@pytest.mark.anyio
async def test_the_same_signal_sizes_by_subscribed_profile() -> None:
    aggressive = await _state(await _account("PROF-AGG-01", "100000.00", "aggressive"))
    conservative = await _state(await _account("PROF-CON-01", "100000.00", "conservative"))

    # 같은 자본·같은 신호인데 성향이 비중을 가른다.
    assert _plan_for(aggressive).quantity == 200  # 20%
    assert _plan_for(conservative).quantity == 100  # 10%


@pytest.mark.anyio
async def test_capital_and_profile_compose() -> None:
    small = await _state(await _account("PROF-AGG-02", "5000.00", "aggressive"))
    large = await _state(await _account("PROF-CON-02", "150000.00", "conservative"))

    assert _plan_for(small).quantity == 10  # 5,000 * 0.20
    assert _plan_for(large).quantity == 150  # 150,000 * 0.10


@pytest.mark.anyio
async def test_the_conservative_cash_floor_actually_binds() -> None:
    # 안전형은 현금 30%를 남겨야 하므로 자본의 70%까지만 투자할 수 있다.
    account = await _state(await _account("PROF-CON-03", "10000.00", "conservative"))

    plan = _plan_for(account, price=10_000.0)

    assert plan.quantity == 0
    assert plan.skipped_reason is not None
