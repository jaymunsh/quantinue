"""The seeded roster: who exists, and which account each one owns."""

from quantinue.db.provisioning import DEMO_ACCOUNTS, DEMO_USERS


def test_exactly_one_administrator_is_seeded() -> None:
    # Given / When
    admins = [spec for spec in DEMO_USERS if spec.role == "admin"]

    # Then
    assert len(admins) == 1
    assert admins[0].broker_account_id is None


def test_every_demo_account_gets_exactly_one_owner() -> None:
    """1유저=1계좌는 부분 유니크 인덱스가 DB로 강제한다 — 명부가 그것을 어기면 안 된다."""
    # Given
    demo_accounts = [spec.broker_account_id for spec in DEMO_ACCOUNTS if not spec.is_test]

    # When
    owned = [spec.broker_account_id for spec in DEMO_USERS if spec.broker_account_id]

    # Then
    assert sorted(owned) == sorted(demo_accounts)
    assert len(owned) == len(set(owned))


def test_test_accounts_stay_ownerless() -> None:
    """관리자 테스트용 계좌라 주인이 없다 — 없는 사람을 지어내지 않는다."""
    # Given
    test_accounts = {spec.broker_account_id for spec in DEMO_ACCOUNTS if spec.is_test}

    # When
    owned = {spec.broker_account_id for spec in DEMO_USERS}

    # Then
    assert test_accounts.isdisjoint(owned)
    assert len(test_accounts) == 2


def test_login_ids_are_unique() -> None:
    # Given / When
    login_ids = [spec.login_id for spec in DEMO_USERS]

    # Then
    assert len(login_ids) == len(set(login_ids))
