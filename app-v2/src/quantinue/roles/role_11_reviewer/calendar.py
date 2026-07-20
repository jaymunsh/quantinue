"""US equity trading dates and close instants used by the T+5 review path.

수제 휴장일 규칙(부활절 산술·이관 규칙 아홉 개)이 살던 파일이다. 잔여 작업 D
에서 그 구현을 지우고 ``core/market_calendar``(exchange_calendars XNYS)에
어댑터로 올라탔다 — 이제 시스템의 달력 구현은 하나다. 얻은 것은 단순화만이
아니다: 수제 규칙은 마감을 16:00 고정으로 알았지만 실물 달력은 반일
세션(7/3 조기 마감 등)의 실제 마감을 안다. 리뷰가 "그날 종가가 확정된
시각"을 묻는 자리라 이 차이는 정확성이다.

XNYS 데이터는 유한하다(현재 2027-07까지). 그 경계를 넘는 T+5를 물으면
``CalendarHorizonError``로 명시적으로 실패한다 — 수제 규칙처럼 무한히 답하는
대신, 모르는 날짜를 지어내지 않는다.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from typing_extensions import override

from quantinue.core.market_calendar import NyseCalendar


@dataclass(frozen=True, slots=True)
class InvalidTradingOffsetError(ValueError):
    """A calendar offset is outside the supported forward range."""

    trading_days: int

    @override
    def __str__(self) -> str:
        """Describe the invalid offset."""
        return f"trading_days must be positive, got {self.trading_days}"


@dataclass(frozen=True, slots=True)
class CalendarHorizonError(ValueError):
    """A date fell beyond the exchange calendar's loaded horizon."""

    start: date
    trading_days: int

    @override
    def __str__(self) -> str:
        """Describe the unanswerable question instead of inventing a date."""
        return (
            f"T+{self.trading_days} from {self.start.isoformat()} is beyond the "
            "loaded XNYS calendar horizon"
        )


class Clock(Protocol):
    """Injectable source of aware UTC time."""

    def now(self) -> datetime:
        """Return the current instant."""
        ...


class TradingCalendar(Protocol):
    """Calendar capability consumed by validation and scheduling."""

    def offset(self, start: date, *, trading_days: int) -> date:
        """Return a future trading session."""
        ...

    def session_close(self, session_date: date) -> datetime:
        """Return an aware UTC close instant."""
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Production wall clock."""

    def now(self) -> datetime:
        """Return the current UTC instant."""
        return datetime.now(UTC)


@dataclass(frozen=True)
class UsEquityTradingCalendar:
    """The review path's calendar, answered by the shared XNYS calendar."""

    exchange: NyseCalendar = field(default_factory=NyseCalendar)

    def offset(self, start: date, *, trading_days: int) -> date:
        """Move forward by an exact positive count of trading sessions."""
        if trading_days < 1:
            raise InvalidTradingOffsetError(trading_days)
        try:
            return self.exchange.add_business_days(start, trading_days)
        except Exception as error:
            # exchange_calendars는 경계 밖에서 자체 예외를 던진다. 그대로
            # 흘리면 호출자가 "달력이 모르는 날짜"와 "버그"를 구별할 수 없다.
            raise CalendarHorizonError(start, trading_days) from error

    def session_close(self, session_date: date) -> datetime:
        """Return the actual session close in UTC — half days included."""
        return self.exchange.session_close(session_date)
