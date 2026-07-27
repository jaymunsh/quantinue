"""The S1~S6 demo scenario contract: one place that fixes every number."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from quantinue.core.market_calendar import NyseCalendar
from quantinue.demo.scripted_events import ScriptedHeadline, scenario_articles
from quantinue.demo.seed import DemoListing, DemoSeedSpec, HeldPosition

if TYPE_CHECKING:
    from quantinue.db.domain_records import RawNewsWrite
    from quantinue.demo.scenario_analyzer import Stance

# 각본 버전. 가격열·사건·기대 결과를 바꾸면 올린다 — 리허설 2회 동일 재현
# 비교는 같은 버전 안에서만 의미가 있다.
SCENARIO_VERSION = "demo-scenario-v1"

# 데모 티커는 실존 종목과 겹치지 않는 가공 심볼이다 — 각본 시세·각본 기사가
# 실제 회사에 대한 진술로 오인되면 안 된다(demo-video-plan.md §1).
DEFENSE_TICKER = "QDEF"  # S2: 급락 → 브래킷 손절
GOOD_TICKER = "QGOD"  # S3: 호재 사건 → 재판단 매수
BAD_TICKER = "QBAD"  # S4: 악재 사건 → 판단 반전 매도

STANCES: dict[str, Stance] = {GOOD_TICKER: "bullish", BAD_TICKER: "bearish"}

_FILM_MINUTES = 240  # 가격열 길이 = 최대 촬영 시간(1분 tick 기준 4시간)


@dataclass(frozen=True, slots=True)
class DemoScenario:
    """Everything the demo runtime assembles from, resolved for one day."""

    trade_date: date
    session_start: datetime
    seed: DemoSeedSpec
    price_paths: dict[str, tuple[Decimal, ...]]
    articles: tuple[RawNewsWrite, ...]


def _flat(price: str, count: int) -> tuple[Decimal, ...]:
    return (Decimal(price),) * count


def _defense_path() -> tuple[Decimal, ...]:
    """안정 → 손절선(139.50) 하회 → 안정. 5번째 tick에 방어선이 발동한다."""
    crash = (*_flat("150.00", 4), Decimal("138.00"))
    return (*crash, *_flat("139.00", _FILM_MINUTES - len(crash)))


def build_scenario(today: date | None = None) -> DemoScenario:
    """Resolve the scripted day against the most recent real NYSE session.

    날짜를 상수로 못 박지 않는 이유: 사건 수집 창과 당일 후보 교집합이
    "실제 오늘" 기준으로 돌기 때문에, 각본 날짜가 과거에 고정되면 기사가
    수집 창 밖으로 밀려 S3·S4가 조용히 죽는다. 대신 "가장 최근 실제 세션"에
    상대적으로 정박한다 — 같은 날 안에서는 몇 번을 돌려도 동일하다.
    """
    calendar = NyseCalendar()
    anchor = today if today is not None else datetime.now(UTC).date()
    trade_date = calendar.previous_trading_day(anchor + timedelta(days=1))
    session_start = calendar.session_open(trade_date)
    cycle_ts = session_start + timedelta(minutes=30)
    seed = DemoSeedSpec(
        trade_date=trade_date,
        cycle_ts=cycle_ts,
        broker_account_id="DEMO-FILM-01",
        opening_cash=Decimal("100000.00"),
        inv_type="aggressive",
        held=(
            HeldPosition(
                listing=DemoListing(
                    ticker=DEFENSE_TICKER, company="Q Defense Demo", sector="Tech"
                ),
                quantity=100,
                entry=Decimal("150.00"),
                stop=Decimal("139.50"),
                take=Decimal("172.50"),
            ),
            HeldPosition(
                listing=DemoListing(
                    ticker=BAD_TICKER, company="Q Bad News Demo", sector="Tech"
                ),
                quantity=200,
                entry=Decimal("80.00"),
                stop=Decimal("64.00"),
                take=Decimal("104.00"),
            ),
        ),
        candidates=(
            DemoListing(ticker=GOOD_TICKER, company="Q Good News Demo", sector="Tech"),
        ),
        users=(),  # 로그인은 seed CLI가 환경변수 비밀번호로 채운다.
    )
    return DemoScenario(
        trade_date=trade_date,
        session_start=session_start,
        seed=seed,
        price_paths={
            DEFENSE_TICKER: _defense_path(),
            # 사건 경로를 격리하기 위해 두 티커의 가격은 ±5% 트리거 아래에
            # 묶어 둔다 — S3·S4의 재판단은 가격이 아니라 기사가 일으킨다.
            GOOD_TICKER: _flat("55.00", _FILM_MINUTES),
            BAD_TICKER: _flat("80.00", _FILM_MINUTES),
        },
        articles=scenario_articles(
            good=ScriptedHeadline(
                ticker=GOOD_TICKER,
                headline="Q Good News Demo, 대형 공급 계약 체결 발표 (각본)",
                at=cycle_ts + timedelta(hours=1),
            ),
            bad=ScriptedHeadline(
                ticker=BAD_TICKER,
                headline="Q Bad News Demo, 연간 가이던스 철회 (각본)",
                at=cycle_ts + timedelta(hours=2),
            ),
        ),
    )
