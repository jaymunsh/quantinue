"""Deterministic scripted market data for the demo runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quantinue.market_data.models import LatestTrade

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime, timedelta
    from decimal import Decimal

_SOURCE = "demo:scripted-trade"


class DemoScenarioError(RuntimeError):
    """Raised when the scripted scenario cannot honestly answer a request.

    데모에서 가격을 지어내 계속 돌면 촬영본이 각본과 다른 이야기를 하게 된다.
    소진·미등록 티커는 조용한 대체값 대신 즉시 실패로 드러낸다
    (demo-video-plan.md §4-1 완료 기준).
    """


class SteppingClock:
    """Walk fixed instants so filming time never leaks into the scenario."""

    def __init__(self, *, start: datetime, step: timedelta) -> None:
        """Bind the deterministic walk; naive datetimes are rejected."""
        # 촬영은 밤·주말에 하지만 각본은 뉴욕 정규장 안에서만 성립한다.
        # naive datetime을 받으면 실행 환경의 로컬 시간대가 몰래 끼어들어
        # 재현성이 깨지므로 여기서 닫는다.
        if start.tzinfo is None:
            msg = "SteppingClock start must be timezone-aware"
            raise DemoScenarioError(msg)
        self._start = start
        self._step = step
        self._ticks = 0

    def __call__(self) -> datetime:
        """Return the next instant of the deterministic walk."""
        instant = self._start + self._step * self._ticks
        self._ticks += 1
        return instant


class ScriptedTradeSource:
    """`LatestTradeSource` that replays a fixed per-ticker price path.

    가격열은 실측 리플레이(실제 급락일의 분봉)에서 왔든 손으로 썼든 같은
    계약으로 소비된다: 호출 순서대로 티커별 커서가 한 칸씩 전진한다.
    """

    def __init__(
        self,
        *,
        paths: Mapping[str, Sequence[Decimal]],
        clock: SteppingClock,
        source: str = _SOURCE,
    ) -> None:
        """Bind immutable price paths and the deterministic clock."""
        for ticker, path in paths.items():
            if not path:
                msg = f"scenario path for {ticker} is empty"
                raise DemoScenarioError(msg)
            if any(price <= 0 for price in path):
                msg = f"scenario path for {ticker} contains a non-positive price"
                raise DemoScenarioError(msg)
        self._paths: dict[str, tuple[Decimal, ...]] = {
            ticker: tuple(path) for ticker, path in paths.items()
        }
        self._cursors: dict[str, int] = dict.fromkeys(self._paths, 0)
        self._clock = clock
        self._source = source

    async def latest_trades(self, tickers: tuple[str, ...]) -> tuple[LatestTrade, ...]:
        """Return the next scripted trade for each requested ticker."""
        observed_at = self._clock()
        trades: list[LatestTrade] = []
        for ticker in tickers:
            path = self._paths.get(ticker)
            if path is None:
                msg = f"ticker {ticker} is not part of the demo scenario"
                raise DemoScenarioError(msg)
            cursor = self._cursors[ticker]
            if cursor >= len(path):
                msg = f"price path for {ticker} is exhausted after {cursor} polls"
                raise DemoScenarioError(msg)
            self._cursors[ticker] = cursor + 1
            trades.append(
                LatestTrade(
                    ticker=ticker,
                    price=path[cursor],
                    observed_at=observed_at,
                    source=self._source,
                )
            )
        return tuple(trades)
