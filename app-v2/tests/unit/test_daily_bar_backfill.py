"""Phase 3 전제: 스크리닝이 랭킹을 매기려면 하루치가 아니라 이력이 있어야 한다.

`ret_20d`·`ma20/50`·`high_252_ratio`·`rsi`는 전부 창(window) 지표다. 지금
수집 잡은 매일 **직전 1세션**만 받으므로, 처음 켠 날 원장에는 봉이 하루치뿐이고
랭킹은 계산 자체가 불가능하다. 백필을 따로 만드는 대신 수집 잡이 "원장이 아는
마지막 날 ~ 직전 세션"을 채우게 하면, 첫 실행은 백필이고 이후 실행은 증분이라
경로가 하나로 남는다.
"""

from datetime import date, timedelta

import httpx as httpx2
import pytest

from quantinue.core.market_calendar import NyseCalendar
from quantinue.db.domain_records import DailyBarWrite
from quantinue.market_data.alpaca_bars import AlpacaBarSource
from quantinue.orchestration.job_factory import build_daily_bars_job

_TODAY = date(2026, 7, 17)


def _page(
    bars: dict[str, list[dict[str, object]]], token: str | None = None
) -> dict[str, object]:
    return {"bars": bars, "next_page_token": token}


def _bar(day: str) -> dict[str, object]:
    return {
        "t": f"{day}T04:00:00Z",
        "o": 100.0,
        "h": 110.0,
        "l": 95.0,
        "c": 105.0,
        "v": 1_000_000,
    }


@pytest.mark.anyio
async def test_a_range_request_asks_for_the_whole_window_at_once() -> None:
    """창 하나를 한 요청으로 — 날짜별로 쪼개면 260콜이 된다."""
    # Given
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200, json=_page({"AAA": [_bar("2026-07-15"), _bar("2026-07-16")]})
        )

    source = AlpacaBarSource(
        key_id="k", secret_key="s", transport=httpx2.MockTransport(handler)
    )

    # When
    bars = await source.daily_bars_range(date(2026, 7, 15), date(2026, 7, 16), ("AAA",))

    # Then: 한 요청, 그리고 각 봉은 자기 날짜로 착지한다.
    assert len(seen) == 1
    assert seen[0].url.params["start"] == "2026-07-15"
    assert seen[0].url.params["end"] == "2026-07-16"
    assert {bar.trade_date for bar in bars} == {date(2026, 7, 15), date(2026, 7, 16)}


class _StubBarSource:
    """Record which window each ticker group was asked for."""

    def __init__(self) -> None:
        self.calls: list[tuple[date, date, tuple[str, ...]]] = []

    async def daily_bars_range(
        self, start: date, end: date, tickers: tuple[str, ...]
    ) -> tuple[DailyBarWrite, ...]:
        self.calls.append((start, end, tickers))
        return ()


class _StubDomain:
    """Ledger stub exposing only what the collection job reads and writes."""

    def __init__(self, coverage: dict[str, date]) -> None:
        self._coverage = coverage
        self.saved: tuple[DailyBarWrite, ...] = ()

    async def bar_coverage(self) -> dict[str, date]:
        return dict(self._coverage)

    async def save_daily_bars(self, bars: tuple[DailyBarWrite, ...]) -> None:
        self.saved = bars


async def _tickers(_: date) -> tuple[str, ...]:
    return ("WARM", "COLD")


@pytest.mark.anyio
async def test_a_ticker_with_no_bars_gets_the_whole_history_window() -> None:
    """봉이 하나도 없는 종목에 증분만 주면 창 지표가 영원히 계산되지 않는다."""
    # Given: WARM은 어제까지 있고 COLD는 원장에 아예 없다.
    source = _StubBarSource()
    domain = _StubDomain({"WARM": date(2026, 7, 15)})
    job = build_daily_bars_job(
        source=source,
        domain=domain,
        tickers=_tickers,
        calendar=NyseCalendar(),
        history_days=260,
    )

    # When
    _ = await job.run(_TODAY)

    # Then: 두 창을 따로 요청한다 — 이미 아는 것을 다시 받지 않기 위해서.
    windows = {call[2]: (call[0], call[1]) for call in source.calls}
    session = NyseCalendar().previous_trading_day(_TODAY)
    assert windows[("COLD",)] == (session - timedelta(days=260), session)
    assert windows[("WARM",)] == (date(2026, 7, 16), session)


@pytest.mark.anyio
async def test_a_stalled_ticker_does_not_drag_the_window_back_for_everyone() -> None:
    """실행마다 수십만 행을 다시 받게 만든 결함 — 실측으로만 잡혔다.

    창의 시작을 가장 **뒤처진** 종목에 맞추면, 상장폐지·거래정지로 봉이 끊긴
    종목 하나가 전 종목의 재수집을 유발한다. 그 종목이 뒤처진 이유는 우리가
    못 받아서가 아니라 거래소에 봉이 없어서이므로, 소급해도 채워지지 않는다.
    """
    # Given: HALTED는 한 달 전에 멈췄고 LIVE는 어제까지 있다.
    session = NyseCalendar().previous_trading_day(_TODAY)
    source = _StubBarSource()
    domain = _StubDomain({"HALTED": date(2026, 6, 15), "LIVE": date(2026, 7, 15)})

    async def both(_: date) -> tuple[str, ...]:
        return ("HALTED", "LIVE")

    job = build_daily_bars_job(
        source=source,
        domain=domain,
        tickers=both,
        calendar=NyseCalendar(),
        history_days=260,
    )

    # When
    _ = await job.run(_TODAY)

    # Then: 앞선 종목 기준으로 하루치만 받는다.
    assert source.calls == [(date(2026, 7, 16), session, ("HALTED", "LIVE"))]


@pytest.mark.anyio
async def test_an_up_to_date_ledger_is_not_asked_for_anything() -> None:
    """이미 직전 세션까지 있으면 외부 API를 두드릴 이유가 없다 — 한도만 축낸다."""
    # Given
    session = NyseCalendar().previous_trading_day(_TODAY)
    source = _StubBarSource()
    domain = _StubDomain({"WARM": session, "COLD": session})
    job = build_daily_bars_job(
        source=source,
        domain=domain,
        tickers=_tickers,
        calendar=NyseCalendar(),
        history_days=260,
    )

    # When
    _ = await job.run(_TODAY)

    # Then
    assert source.calls == []
