"""Single source of truth for the order idempotency key.

이 키는 두 곳에서 같은 뜻으로 쓰인다: 브로커 제출의 ``client_order_id``와
``tb_order.idempotency_key``. 둘이 갈라지면 재시도가 중복 주문이 되거나,
반대로 서로 다른 주문이 한 건으로 합쳐진다. 그래서 파생 규칙은 하나여야 한다
— 예전엔 role_09와 role_10에 같은 문자열이 각자 박혀 있었다.
"""

from typing import Final

# Alpaca의 client_order_id 상한. broker/contracts.py의 OrderPlan도 같은 값으로
# 필드를 제한한다 — 넘치면 제출 자체가 실패한다.
MAX_CLIENT_ORDER_ID_LENGTH: Final = 48

_CLOSE_SUFFIX: Final = "-c"


def derive_client_order_id(*, account_id: int, signal_id: int, is_close: bool = False) -> str:
    """Derive the stable key from the dimensions that make an order unique.

    계좌와 시그널이 유일성의 두 축이다. 계좌를 빼면 다계좌 팬아웃에서 키가
    겹쳐 나머지 계좌가 조용히 체결된 것처럼 보이고, 시그널을 빼면 같은 계좌의
    다른 판단이 한 건으로 합쳐진다.

    청산은 접미사로 갈라놓는다. 청산은 자기 sell 시그널을 갖지만(D7), 그래도
    접미사를 붙이는 이유는 사람이 로그에서 키만 보고 방향을 알 수 있어야 하고,
    시그널 발급이 어긋난 경우에도 매수와 절대 충돌하지 않게 하기 위해서다.
    """
    key = f"q-a{account_id}-s{signal_id}"
    if is_close:
        key = f"{key}{_CLOSE_SUFFIX}"
    if len(key) > MAX_CLIENT_ORDER_ID_LENGTH:
        message = f"derived client_order_id exceeds {MAX_CLIENT_ORDER_ID_LENGTH} characters"
        raise ValueError(message)
    return key
