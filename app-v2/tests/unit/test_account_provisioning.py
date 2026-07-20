"""The canonical account roster is data, not a script's side effect.

Keeping the roster in a module means the amounts and investment types can be
asserted without a database, and the provisioning script becomes a thin caller.
"""

from decimal import Decimal

from quantinue.db.provisioning import DEMO_ACCOUNTS, TEST_ACCOUNT_PREFIX, account_writes


def test_the_roster_matches_the_agreed_structure() -> None:
    # 2026-07-19 확정: 테스트 2($100K 공격·안전) + 데모 5.
    by_id = {spec.broker_account_id: spec for spec in DEMO_ACCOUNTS}

    assert len(DEMO_ACCOUNTS) == 7
    assert sum(1 for spec in DEMO_ACCOUNTS if spec.is_test) == 2
    assert by_id["TEST-AGGRESSIVE-01"].equity == Decimal("100000.00")
    assert by_id["TEST-CONSERVATIVE-01"].equity == Decimal("100000.00")


def test_demo_amounts_are_the_revised_ones() -> None:
    aggressive = sorted(
        spec.equity
        for spec in DEMO_ACCOUNTS
        if spec.inv_type == "aggressive" and not spec.is_test
    )
    conservative = sorted(
        spec.equity
        for spec in DEMO_ACCOUNTS
        if spec.inv_type == "conservative" and not spec.is_test
    )

    # 기존 $1M·$50K 안은 폐기됐다.
    assert aggressive == [Decimal("5000.00"), Decimal("100000.00"), Decimal("150000.00")]
    assert conservative == [Decimal("5000.00"), Decimal("100000.00")]


def test_test_accounts_are_identifiable_by_prefix() -> None:
    for spec in DEMO_ACCOUNTS:
        assert spec.is_test == spec.broker_account_id.startswith(TEST_ACCOUNT_PREFIX)


def test_a_fresh_account_starts_fully_in_cash() -> None:
    # 아직 아무것도 사지 않았으므로 현금 = 자본이어야 한다.
    for write in account_writes():
        assert write.cash == write.equity
        assert write.buying_power == write.equity


def test_every_account_declares_an_investment_type() -> None:
    # inv_type이 없으면 프로필을 고를 수 없다(M6-1 계좌 구독 루프의 전제).
    assert all(write.inv_type in {"aggressive", "conservative"} for write in account_writes())
