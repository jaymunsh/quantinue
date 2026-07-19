"""Portfolio limits come from the account and the profile, not from constants.

`max_positions`·`max_weight`·`min_cash_ratio` sat in config with no consumer
since M2, while role 09 sized against its own literals. Worse, `max_weight` and
`POSITION_CAP_FRACTION` were the same idea expressed twice — one live, one dead.
"""

from datetime import UTC, datetime

import pytest

from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.orchestration.policy import ProfileConfig
from quantinue.roles.role_09_risk_portfolio.contracts import (
    RiskPortfolioInput,
    RiskPortfolioOutput,
    build_order_plan,
)

AGGRESSIVE = ProfileConfig()  # max_positions 10 · max_weight 0.20 · min_cash 0.10
CONSERVATIVE = ProfileConfig(
    max_positions=5, max_weight=0.10, min_cash_ratio=0.30, buy_threshold=0.75
)
NOW = datetime(2026, 7, 20, 17, 0, tzinfo=UTC)

_EVIDENCE = Evidence(
    evidence_id="run-circuit:08:critic",
    run_id="run-circuit",
    source="critic",
    source_ref="policy://critic/v1",
    observed_at=NOW,
    captured_at=NOW,
    confidence=1.0,
    kind=EvidenceKind.MODEL_OUTPUT,
)


def _plan_input(**changes: object) -> RiskPortfolioInput:
    values: dict[str, object] = {
        "run_id": "run-circuit",
        "execution_at": NOW,
        "evidence": (_EVIDENCE,),
        "signal_id": 1,
        "account_id": 1,
        "ticker": "NVDA",
        "cycle_ts": NOW,
        "critic_approved": True,
        "current_price": 100.0,
        "equity": 100_000.0,
        "cash": 100_000.0,
        "daily_new_order_cap": 5,
        "risk_score": 0.0,
    }
    return RiskPortfolioInput.model_validate({**values, **changes})


def _plan(profile: ProfileConfig, **changes: object) -> RiskPortfolioOutput:
    return build_order_plan(_plan_input(**changes), profile=profile)


def test_position_size_is_capped_by_the_profile_weight_not_a_constant() -> None:
    aggressive = _plan(AGGRESSIVE)
    conservative = _plan(CONSERVATIVE)

    # 자본 $100,000 · 주가 $100 → 공격 20% = 200주 / 안전 10% = 100주
    assert aggressive.quantity == 200
    assert conservative.quantity == 100


def test_a_full_book_blocks_a_new_position() -> None:
    at_limit = _plan(AGGRESSIVE, open_position_count=10)
    below = _plan(AGGRESSIVE, open_position_count=9)

    assert at_limit.quantity == 0
    assert at_limit.skipped_reason == "max_positions"
    assert below.skipped_reason is None


def test_the_conservative_book_fills_up_sooner() -> None:
    five = _plan(CONSERVATIVE, open_position_count=5)

    assert five.skipped_reason == "max_positions"
    assert _plan(AGGRESSIVE, open_position_count=5).skipped_reason is None


def test_the_cash_floor_stops_the_last_affordable_buy() -> None:
    # 현금 $15,000 남았는데 20% 포지션($20,000)은 바닥을 뚫는다.
    plan = _plan(AGGRESSIVE, cash=15_000.0)

    assert plan.quantity == 0
    assert plan.skipped_reason == "min_cash"


def test_the_cash_floor_is_a_floor_not_a_ban() -> None:
    # 현금이 넉넉하면 같은 주문이 통과해야 한다.
    assert _plan(AGGRESSIVE, cash=90_000.0).skipped_reason is None


def test_the_conservative_floor_is_higher() -> None:
    # 현금 40%: 공격형(10% 유지)은 통과, 안전형(30% 유지)은 차단.
    assert _plan(AGGRESSIVE, cash=40_000.0).skipped_reason is None
    assert _plan(CONSERVATIVE, cash=32_000.0).skipped_reason == "min_cash"


def test_sizing_uses_account_equity_rather_than_an_app_wide_cap() -> None:
    # $5,000 계좌는 $150,000 계좌와 같은 주문을 내면 안 된다.
    small = _plan(AGGRESSIVE, equity=5_000.0, cash=5_000.0)
    large = _plan(AGGRESSIVE, equity=150_000.0, cash=150_000.0)

    assert small.quantity == 10  # 5,000 * 0.20 / 100
    assert large.quantity == 300  # 150,000 * 0.20 / 100


@pytest.mark.parametrize("profile", [AGGRESSIVE, CONSERVATIVE])
def test_an_unaffordable_account_is_skipped_not_crashed(profile: ProfileConfig) -> None:
    plan = _plan(profile, equity=50.0, cash=50.0, current_price=100.0)

    assert plan.quantity == 0
    assert plan.skipped_reason is not None
