"""Phase 1b: decide whether a day's range triggered a protective bracket leg."""

from decimal import Decimal

import pytest

from quantinue.broker.bracket_trigger import (
    BracketLeg,
    DailyRange,
    evaluate_bracket,
)

_STOP = Decimal("85.00")
_TAKE = Decimal("120.00")


def _range(low: str, high: str) -> DailyRange:
    return DailyRange(low=Decimal(low), high=Decimal(high))


def test_a_quiet_day_inside_the_bracket_triggers_nothing() -> None:
    """Neither leg touched means the position stays open."""
    # Given/When
    leg = evaluate_bracket(_range("95.00", "110.00"), stop=_STOP, take_profit=_TAKE)

    # Then
    assert leg is None


def test_low_touching_the_stop_triggers_the_stop() -> None:
    """A stop is a resting order — trading at the price is enough to fill it."""
    # Given/When
    leg = evaluate_bracket(_range("85.00", "110.00"), stop=_STOP, take_profit=_TAKE)

    # Then
    assert leg is BracketLeg.STOP


def test_high_reaching_the_take_profit_triggers_the_target() -> None:
    # Given/When
    leg = evaluate_bracket(_range("95.00", "120.00"), stop=_STOP, take_profit=_TAKE)

    # Then
    assert leg is BracketLeg.TAKE_PROFIT


def test_a_day_that_touched_both_legs_resolves_to_the_stop() -> None:
    """D5: 일봉으로는 장중 순서를 알 수 없다 — 보수적으로 손절을 택한다.

    익절을 택하면 실제로는 손절 후 반등한 날을 이익으로 기록해 성과가
    부풀려지고, T+5 학습이 그 거짓을 진실로 배운다.
    """
    # Given/When
    leg = evaluate_bracket(_range("80.00", "125.00"), stop=_STOP, take_profit=_TAKE)

    # Then
    assert leg is BracketLeg.STOP


def test_a_gap_down_below_the_stop_still_triggers_the_stop() -> None:
    """갭 하락이면 손절가에 못 팔지만, 발동 여부 판정은 별개다."""
    # Given/When
    leg = evaluate_bracket(_range("70.00", "75.00"), stop=_STOP, take_profit=_TAKE)

    # Then
    assert leg is BracketLeg.STOP


def test_an_inverted_range_is_rejected() -> None:
    """low > high is not a real bar — accepting it would hide upstream corruption."""
    # Given/When/Then
    with pytest.raises(ValueError, match="low"):
        _ = DailyRange(low=Decimal("120.00"), high=Decimal("100.00"))
