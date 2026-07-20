"""Password hashing contract for the two-sided web login."""

from quantinue.api.passwords import hash_password, verify_password


def test_hash_never_contains_the_plaintext() -> None:
    # Given / When
    stored = hash_password("correct horse battery staple")

    # Then
    assert "correct horse battery staple" not in stored
    assert stored.startswith("$argon2")


def test_same_password_hashes_differently_each_time() -> None:
    """A per-hash salt means two identical passwords are not linkable in the ledger."""
    # Given / When
    first = hash_password("same-secret")
    second = hash_password("same-secret")

    # Then
    assert first != second


def test_verify_accepts_the_original_password() -> None:
    # Given
    stored = hash_password("s3cret-value")

    # When / Then
    assert verify_password(stored, "s3cret-value") is True


def test_verify_rejects_a_wrong_password() -> None:
    # Given
    stored = hash_password("s3cret-value")

    # When / Then
    assert verify_password(stored, "s3cret-valuf") is False


def test_verify_rejects_an_account_with_no_stored_hash() -> None:
    """password_hash is nullable, and a row without one must be unloggable-into.

    비어 있는 해시를 "검증 생략"으로 읽으면 비밀번호를 아직 정하지 않은 계정이
    아무 입력으로나 열린다. 없는 것은 통과가 아니라 거절이다.
    """
    # Given / When / Then
    assert verify_password(None, "anything") is False
    assert verify_password("", "anything") is False


def test_verify_rejects_a_corrupt_stored_hash() -> None:
    """A malformed hash is a rejection, not a crash that leaks account existence."""
    # Given / When / Then
    assert verify_password("not-an-argon2-hash", "anything") is False
