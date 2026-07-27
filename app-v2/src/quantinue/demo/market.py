"""Scripted market-data source so the demo runs the *whole* job chain.

데모에 시세·유니버스·매크로 소스를 물리지 않으면 `universe`·`daily_bars`·
`benchmark`·`macro` 잡이 **등록조차 되지 않는다**(job_factory는 소스가 없는
수집 잡을 건너뛴다). 그러면 관제실이 잡 9개만 보여주는데, 실제 시스템은
13개다 — 화면이 시스템을 축소해 보여주는 셈이라 촬영본으로 못 쓴다.

여기 있는 소스는 각본 종목과 배경 종목의 시세를 **결정론으로** 만들어
그 네 잡을 되살린다. 값은 지어내되 규칙이 고정이라 몇 번을 돌려도 같다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from quantinue.db.domain_records import DailyBarWrite
from quantinue.market_data.models import (
    MacroObservation,
    Provenance,
    SecuritySnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

_SOURCE = "demo:scripted-market"
_AT = datetime(2026, 7, 24, 20, tzinfo=UTC)


def _provenance(execution_id: str) -> Provenance:
    return Provenance(
        source=_SOURCE,
        source_ref="demo://scripted-market",
        observed_at=_AT,
        captured_at=_AT,
        confidence=1.0,
        execution_id=execution_id,
    )


class DemoMarketData:
    """Universe, bars, and macro for exactly the tickers the scenario knows.

    각본 밖 종목을 절대 만들지 않는 것이 계약이다 — 유니버스에 없는 종목이
    픽으로 올라오면 감시 루프가 각본에 없는 시세를 요구하고 그 자리에서
    `DemoScenarioError`로 죽는다.
    """

    def __init__(
        self,
        *,
        listings: Mapping[str, tuple[str, Decimal]],
        featured: frozenset[str],
    ) -> None:
        """Bind ticker → (company, reference price) and which ones rank first."""
        self._listings = dict(listings)
        self._featured = featured

    async def screener(self, execution_id: str) -> tuple[SecuritySnapshot, ...]:
        """Return the demo universe as one stable listing feed."""
        return tuple(
            SecuritySnapshot(
                ticker=ticker,
                name=company,
                # 각본 종목을 크게 잡아 스크리닝 상위에 서게 한다 — 배경
                # 종목이 판단 대상을 밀어내면 장면이 통째로 흐려진다.
                market_cap=Decimal(900_000_000_000 if ticker in self._featured else 4_000_000_000),
                last_price=price,
                volume=40_000_000 if ticker in self._featured else 1_200_000,
                provenance=_provenance(execution_id),
            )
            for ticker, (company, price) in self._listings.items()
        )

    async def daily_bars_range(
        self, start: date, end: date, tickers: tuple[str, ...]
    ) -> tuple[DailyBarWrite, ...]:
        """Return a deterministic upward drift for every requested session.

        완전 평탄한 봉은 기술 지표를 0으로 나누는 자리를 만든다. 하루
        0.3%씩 오르는 아주 완만한 기울기를 주되 각본 가격(마지막 세션)에
        착지시켜 감시 가격과 어긋나지 않게 한다.
        """
        bars: list[DailyBarWrite] = []
        span = max((end - start).days, 1)
        for ticker in tickers:
            listing = self._listings.get(ticker)
            if listing is None:
                continue
            _, reference = listing
            current = start
            while current <= end:
                # 마지막 날이 기준가, 첫날은 그 80%. 하루씩 빼는 방식은 창이
                # 길어지면(history_days 400일) 값이 음수로 내려가 봉 제약을
                # 위반한다 — 실제로 밟았다. 비율로 잡아 항상 양수로 둔다.
                progress = Decimal((current - start).days) / Decimal(span)
                factor = Decimal("0.80") + (Decimal("0.20") * progress)
                close = (reference * factor).quantize(Decimal("0.01"))
                bars.append(
                    DailyBarWrite(
                        trade_date=current,
                        ticker=ticker,
                        open=close,
                        high=(close * Decimal("1.004")).quantize(Decimal("0.01")),
                        low=(close * Decimal("0.996")).quantize(Decimal("0.01")),
                        close=close,
                        volume=1_000_000 + (span * 1_000),
                        source=_SOURCE,
                    )
                )
                current += timedelta(days=1)
        return tuple(bars)

    async def macro(self, series: str, execution_id: str) -> tuple[MacroObservation, ...]:
        """Return one stable rate observation so the regime job has an input."""
        return (
            MacroObservation(
                series=series,
                observed_at=_AT,
                value=Decimal("4.25"),
                provenance=_provenance(execution_id),
            ),
        )
