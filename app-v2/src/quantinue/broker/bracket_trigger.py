"""Decide whether a trading day's range triggered a protective bracket leg.

실 브로커에 붙어 있을 때는 브래킷이 거래소에 상주하며 장중에 스스로 발동한다.
로컬 시뮬 체결(재설계 D1)에서는 그 역할을 우리가 해야 하는데, 우리가 가진
가장 세밀한 관측은 일봉이다. 그래서 "그날의 고저가 손절·익절 선을 건드렸는가"로
발동을 판정한다.

이건 근사다. 장중 틱을 보면 알 수 있었을 것들이 여기서는 하루 단위로 뭉개진다.
그 한계와 개선 경로는 future-roadmap.md R7에 적어뒀다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


@unique
class BracketLeg(StrEnum):
    """Which protective leg a day's range triggered."""

    STOP = "stop"
    TAKE_PROFIT = "take_profit"


@dataclass(frozen=True, slots=True)
class DailyRange:
    """One trading day's low and high, the only intraday detail a bar carries."""

    low: Decimal
    high: Decimal

    def __post_init__(self) -> None:
        """Reject a bar that cannot exist rather than silently trading on it."""
        if self.low > self.high:
            message = "daily range low must not exceed high"
            raise ValueError(message)


def evaluate_bracket(
    day: DailyRange,
    *,
    stop: Decimal,
    take_profit: Decimal,
) -> BracketLeg | None:
    """Return the leg this day triggered, or None when the position survived.

    경계값은 '닿으면 발동'으로 본다(``<=``/``>=``). 손절·익절은 거래소에 걸려
    있는 대기 주문이라 그 가격에 거래가 성립하면 체결되기 때문이다.

    둘 다 닿은 날은 **손절로 판정한다**(재설계 D5). 일봉에는 순서 정보가 없어
    어느 쪽이 먼저였는지 알 수 없는데, 익절로 찍으면 실제로는 손절당한 뒤
    반등한 날이 이익으로 기록된다. 그렇게 부풀려진 성과는 T+5 학습 루프가
    그대로 진실로 배우기 때문에, 틀리더라도 불리한 쪽으로 틀리는 편이 낫다.
    """
    hit_stop = day.low <= stop
    hit_take_profit = day.high >= take_profit
    if hit_stop:
        return BracketLeg.STOP
    if hit_take_profit:
        return BracketLeg.TAKE_PROFIT
    return None
