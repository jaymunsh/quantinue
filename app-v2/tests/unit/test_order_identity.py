"""Phase 1a: one shared derivation for the broker/ledger idempotency key."""


from quantinue.core.order_identity import MAX_CLIENT_ORDER_ID_LENGTH, derive_client_order_id


def test_entry_and_close_for_the_same_signal_get_distinct_keys() -> None:
    """A close must not collide with the entry it closes.

    같은 키를 쓰면 브로커가 청산을 매수의 재시도로 보고 삼켜버린다 —
    포지션은 그대로인데 원장에는 청산이 있는 상태가 된다.
    """
    # Given/When
    entry = derive_client_order_id(account_id=1, signal_id=7)
    close = derive_client_order_id(account_id=1, signal_id=7, is_close=True)

    # Then
    assert entry != close


def test_key_is_stable_for_the_same_inputs() -> None:
    """Idempotency depends on the key being a pure function of its inputs."""
    # Given/When/Then
    assert derive_client_order_id(account_id=2, signal_id=9) == derive_client_order_id(
        account_id=2, signal_id=9
    )


def test_accounts_do_not_share_a_key_for_the_same_signal() -> None:
    """계좌별 팬아웃에서 키가 겹치면 나머지 계좌가 조용히 체결된 것처럼 보인다."""
    # Given/When/Then
    assert derive_client_order_id(account_id=1, signal_id=7) != derive_client_order_id(
        account_id=2, signal_id=7
    )


def test_key_fits_the_broker_field_limit() -> None:
    """Alpaca's client_order_id is bounded — an overflow is a submission failure."""
    # Given/When
    entry = derive_client_order_id(account_id=999_999_999, signal_id=999_999_999_999)
    close = derive_client_order_id(
        account_id=999_999_999, signal_id=999_999_999_999, is_close=True
    )

    # Then
    assert len(entry) <= MAX_CLIENT_ORDER_ID_LENGTH
    assert len(close) <= MAX_CLIENT_ORDER_ID_LENGTH
