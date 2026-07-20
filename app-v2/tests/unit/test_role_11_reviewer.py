from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quantinue.roles.role_11_reviewer.calendar import (
    CalendarHorizonError,
    UsEquityTradingCalendar,
)
from quantinue.roles.role_11_reviewer.contracts import (
    ReviewInput,
    ReviewOutput,
    ReviewPriceSnapshot,
    ReviewSignal,
)

_DECIDED_AT = datetime(2026, 7, 13, 19, 0, tzinfo=UTC)
_CAPTURED_AT = datetime(2026, 7, 21, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def signal(*, signal_id: int, side: str, filled: int | None = None) -> ReviewSignal:
    return ReviewSignal.model_validate(
        {
            "run_id": "run-11",
            "signal_id": signal_id,
            "side": side,
            "trade_date": date(2026, 7, 13),
            "decided_at": _DECIDED_AT,
            "evidence_ids": ("signal-evidence",),
            "not_applicable": (
                ({"dimension": "filled_price", "reason": "hold has no broker fill"},)
                if side == "hold"
                else ()
            ),
            "filled_price": Decimal(filled) if filled is not None else None,
            "decision_close": Decimal(100),
        },
        strict=True,
    )


def snapshot(offset: int, close: int, *, price_date: date | None = None) -> ReviewPriceSnapshot:
    calendar = UsEquityTradingCalendar()
    session_date = price_date or calendar.offset(date(2026, 7, 13), trading_days=offset)
    return ReviewPriceSnapshot(
        run_id="run-11",
        evidence_id=f"price-{offset}",
        parent_evidence_ids=("signal-evidence",),
        day_offset=offset,
        price_date=session_date,
        close=Decimal(close),
        observed_at=calendar.session_close(session_date),
        captured_at=_CAPTURED_AT,
    )


def test_fifth_trading_day_skips_weekend_and_independence_day() -> None:
    # Given
    calendar = UsEquityTradingCalendar()
    # When
    due_date = calendar.offset(date(2026, 7, 1), trading_days=5)
    # Then
    assert due_date == date(2026, 7, 9)


def test_t_plus_five_spans_dst_and_weekend() -> None:
    # Given
    calendar = UsEquityTradingCalendar()
    # When
    due_date = calendar.offset(date(2026, 10, 30), trading_days=5)
    due_close = calendar.session_close(due_date)
    # Then
    assert due_date == date(2026, 11, 6)
    assert due_close == datetime(2026, 11, 6, 21, 0, tzinfo=UTC)


def test_session_close_utc_tracks_new_york_dst() -> None:
    # Given
    calendar = UsEquityTradingCalendar()
    # When
    summer_close = calendar.session_close(date(2026, 7, 13))
    winter_close = calendar.session_close(date(2026, 12, 14))
    # Then
    assert (summer_close.hour, winter_close.hour) == (20, 21)


def test_buy_and_hold_require_their_contractual_base() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match="filled_price"):
        _ = ReviewSignal(
            run_id="run-11",
            signal_id=1,
            side="buy",
            trade_date=date(2026, 7, 13),
            decided_at=_DECIDED_AT,
            evidence_ids=("evidence",),
            not_applicable=(),
            decision_close=Decimal(100),
        )


def test_review_output_forbids_caller_supplied_numeric_result() -> None:
    # Given
    request = ReviewInput(
        signal=signal(signal_id=4, side="hold"),
        snapshots=tuple(snapshot(offset, 100) for offset in range(1, 6)),
    )
    # When / Then
    with pytest.raises(ValidationError, match="ret_5d"):
        _ = ReviewOutput.model_validate(
            {
                "review_input": request,
                "reviewed_at": _CAPTURED_AT,
                "lesson": "임의 숫자 차단",
                "ret_5d": 999.0,
            },
            strict=True,
        )


def test_snapshot_rejects_observation_after_capture() -> None:
    # Given
    session_date = date(2026, 7, 14)
    # When / Then
    with pytest.raises(ValidationError, match="observed_at"):
        _ = ReviewPriceSnapshot(
            run_id="run-11",
            evidence_id="future-price",
            parent_evidence_ids=("signal-evidence",),
            day_offset=1,
            price_date=session_date,
            close=Decimal(101),
            observed_at=datetime(2026, 7, 14, 21, 0, tzinfo=UTC),
            captured_at=datetime(2026, 7, 14, 20, 0, tzinfo=UTC),
        )


def test_a_question_beyond_the_calendar_horizon_fails_loudly() -> None:
    """수제 규칙은 무한히 답했다 — 실물 달력은 모르는 날짜를 지어내지 않는다.

    잔여 작업 D의 대체 테스트다: 두 캘린더의 어긋남 감시(test_calendar_agreement)
    는 구현이 하나가 되면서 대상을 잃었고, 남는 위험은 XNYS 데이터 경계다.
    """
    calendar = UsEquityTradingCalendar()

    with pytest.raises(CalendarHorizonError):
        _ = calendar.offset(date(2027, 7, 19), trading_days=5)


def test_a_half_day_session_closes_early_not_at_four() -> None:
    """반일 세션의 실제 마감 — 수제 16:00 고정 규칙이 틀리던 지점이다.

    2026-11-27(추수감사절 다음 금요일)은 13:00 뉴욕 마감이다. 리뷰는 "종가가
    확정된 시각"을 묻는 자리라 세 시간 이르게 여는 것이 정확성이다.
    """
    calendar = UsEquityTradingCalendar()

    close = calendar.session_close(date(2026, 11, 27))

    assert close == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)  # 13:00 New York
