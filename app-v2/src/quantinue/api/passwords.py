"""Password hashing for the admin/user web login."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

# 파라미터를 우리가 고르지 않고 라이브러리 기본값을 쓴다. argon2-cffi의 기본은
# OWASP 권고를 따라 갱신되므로, 우리가 숫자를 박으면 그 갱신을 놓치고 문턱을
# 코드가 소유하게 된다. 튜닝이 필요해지는 날 config로 올린다.
_HASHER = PasswordHasher()

# 저장된 해시가 없을 때도 같은 비용을 치르기 위한 더미. 없는 계정은 즉시
# 거절되고 있는 계정만 해시 검증에 시간을 쓰면, 응답 시간이 "그 아이디가
# 있느냐"를 알려준다. 로그인 실패 문구를 통일해놓고 시간으로 새면 소용없다.
_DUMMY_HASH = _HASHER.hash("quantinue-timing-equalizer")


def hash_password(plaintext: str) -> str:
    """Return a salted argon2 hash; the plaintext is never persisted anywhere."""
    return _HASHER.hash(plaintext)


def verify_password(stored_hash: str | None, plaintext: str) -> bool:
    """Report whether the plaintext matches, treating a missing hash as a rejection."""
    if not stored_hash:
        # 비교할 것이 없어도 같은 시간을 쓴다 — 위 _DUMMY_HASH 주석 참조.
        _verify_or_false(_DUMMY_HASH, plaintext)
        return False
    return _verify_or_false(stored_hash, plaintext)


def _verify_or_false(stored_hash: str, plaintext: str) -> bool:
    """Collapse every argon2 failure mode into a plain rejection."""
    try:
        return _HASHER.verify(stored_hash, plaintext)
    except (Argon2Error, InvalidHashError):
        # 손상된 해시도 거절이지 예외가 아니다. 여기서 터지면 500이 나가고,
        # 500과 로그인 실패의 차이가 계정 존재 여부를 알려준다.
        return False
