"""Scripted demo market source: deterministic replay for filming."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from quantinue.core.market_calendar import NEW_YORK, NyseCalendar
from quantinue.demo.scripted_market import (
    DemoScenarioError,
    ScriptedTradeSource,
    SteppingClock,
)

# 2026-07-24(금)은 실제 거래일이다 — 운영 원장에도 슬롯이 있다. 데모 시계는
# 이 정규장 안에서만 걷는다: 촬영이 밤이든 주말이든 정규장 게이트를 통과해야
# 각본이 재현되기 때문이다.
_SESSION_START = datetime(2026, 7, 24, 10, 30, tzinfo=NEW_YORK)

_PATHS = {
    "NVDA": (Decimal("150.00"), Decimal("138.00"), Decimal("139.00")),
    "AAPL": (Decimal("210.00"), Decimal("211.00")),
}


def _clock() -> SteppingClock:
    return SteppingClock(start=_SESSION_START, step=timedelta(minutes=1))


class TestSteppingClock:
    def test_same_arguments_walk_the_same_instants(self) -> None:
        first = _clock()
        second = _clock()
        assert [first() for _ in range(3)] == [second() for _ in range(3)]

    def test_every_instant_stays_inside_the_regular_session(self) -> None:
        calendar = NyseCalendar()
        clock = _clock()
        assert all(calendar.is_market_open(clock()) for _ in range(30))

    def test_naive_start_is_rejected(self) -> None:
        with pytest.raises(DemoScenarioError):
            SteppingClock(start=datetime(2026, 7, 24, 10, 30), step=timedelta(minutes=1))  # noqa: DTZ001


class TestScriptedTradeSource:
    @pytest.mark.anyio
    async def test_same_scenario_replays_identical_price_sequences(self) -> None:
        async def drain(source: ScriptedTradeSource) -> list[Decimal]:
            prices: list[Decimal] = []
            for _ in range(3):
                (trade,) = await source.latest_trades(("NVDA",))
                prices.append(trade.price)
            return prices

        first = ScriptedTradeSource(paths=_PATHS, clock=_clock())
        second = ScriptedTradeSource(paths=_PATHS, clock=_clock())
        assert await drain(first) == await drain(second)
        assert await drain(ScriptedTradeSource(paths=_PATHS, clock=_clock())) == [
            Decimal("150.00"),
            Decimal("138.00"),
            Decimal("139.00"),
        ]

    @pytest.mark.anyio
    async def test_each_ticker_advances_independently(self) -> None:
        source = ScriptedTradeSource(paths=_PATHS, clock=_clock())
        (nvda,) = await source.latest_trades(("NVDA",))
        (nvda_second,) = await source.latest_trades(("NVDA",))
        (aapl,) = await source.latest_trades(("AAPL",))
        assert (nvda.price, nvda_second.price) == (Decimal("150.00"), Decimal("138.00"))
        assert aapl.price == Decimal("210.00")

    @pytest.mark.anyio
    async def test_trades_carry_clock_instants_and_demo_source(self) -> None:
        source = ScriptedTradeSource(paths=_PATHS, clock=_clock())
        (first,) = await source.latest_trades(("NVDA",))
        (second,) = await source.latest_trades(("NVDA",))
        assert first.source == "demo:scripted-trade"
        assert second.observed_at > first.observed_at

    @pytest.mark.anyio
    async def test_exhausted_path_fails_loudly_instead_of_inventing_prices(self) -> None:
        source = ScriptedTradeSource(
            paths={"NVDA": (Decimal("150.00"),)}, clock=_clock()
        )
        await source.latest_trades(("NVDA",))
        with pytest.raises(DemoScenarioError, match="exhausted"):
            await source.latest_trades(("NVDA",))

    @pytest.mark.anyio
    async def test_unknown_ticker_fails_loudly(self) -> None:
        source = ScriptedTradeSource(paths=_PATHS, clock=_clock())
        with pytest.raises(DemoScenarioError, match="TSLA"):
            await source.latest_trades(("TSLA",))

    def test_empty_path_is_rejected_at_construction(self) -> None:
        with pytest.raises(DemoScenarioError):
            ScriptedTradeSource(paths={"NVDA": ()}, clock=_clock())
