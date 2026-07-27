"""The S1~S6 demo scenario contract: one place that fixes every number."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from quantinue.core.market_calendar import NyseCalendar
from quantinue.demo.background import (
    BACKGROUND_LISTINGS,
    background_articles,
    background_filings,
)
from quantinue.demo.scripted_events import ScriptedHeadline, scenario_articles
from quantinue.demo.seed import DemoListing, DemoSeedSpec, HeldPosition

if TYPE_CHECKING:
    from quantinue.db.domain_records import RawDisclosureWrite, RawNewsWrite
    from quantinue.demo.scenario_analyzer import Stance

# 각본 버전. 가격열·사건·기대 결과를 바꾸면 올린다 — 리허설 2회 동일 재현
# 비교는 같은 버전 안에서만 의미가 있다.
SCENARIO_VERSION = "demo-scenario-v3"

# 데모 티커는 실존 종목과 겹치지 않는 **가상 회사**다. 두 가지를 동시에
# 피해야 한다: 실존 종목을 쓰면 각본 기사가 그 회사에 대한 진술로 오인되고,
# QGOD/QBAD처럼 용도를 이름에 박으면 화면이 각본임을 스스로 폭로해 시연의
# 설득력을 깎는다. 정직성은 화면의 mock 배지와 내레이션이 담당한다
# (demo-video-plan.md §1).
DEFENSE_TICKER = "VRDN"  # S2: 급락 → 브래킷 손절
GOOD_TICKER = "NVEX"  # S3: 호재 사건 → 재판단 매수
BAD_TICKER = "HLXM"  # S4: 악재 사건 → 판단 반전 매도

DEFENSE_COMPANY = "Veridian Dynamics"
GOOD_COMPANY = "Novexa Robotics"
BAD_COMPANY = "Helixim Materials"

DEMO_ACCOUNT_ID = "QUANTINUE-DEMO-01"

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
    wire_articles: tuple[RawNewsWrite, ...]
    filings: tuple[RawDisclosureWrite, ...]
    listings: dict[str, tuple[str, Decimal]]
    featured: frozenset[str]


def _flat(price: str, count: int) -> tuple[Decimal, ...]:
    return (Decimal(price),) * count


def _background_listings() -> dict[str, tuple[str, Decimal]]:
    """Give the background tickers a stable price so nothing crashes.

    유니버스에 있는 종목은 픽으로 올라올 수 있고, 픽이 되면 감시 루프가
    시세를 묻는다. 각본에 값이 없으면 그 자리에서 죽으므로 전부 값을 준다.
    가격은 티커 문자로 정해 회차마다 흔들리지 않는다.
    """
    return {
        ticker: (company, Decimal(20 + (index * 7) % 130))
        for index, (ticker, company) in enumerate(BACKGROUND_LISTINGS)
    }


def _all_listings() -> dict[str, tuple[str, Decimal]]:
    """Scenario tickers first, then background — the demo's whole universe."""
    return {
        DEFENSE_TICKER: (DEFENSE_COMPANY, Decimal("150.00")),
        GOOD_TICKER: (GOOD_COMPANY, Decimal("55.00")),
        BAD_TICKER: (BAD_COMPANY, Decimal("80.00")),
        **_background_listings(),
    }


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
    previous_session = calendar.previous_trading_day(trade_date)
    seed = DemoSeedSpec(
        trade_date=trade_date,
        cycle_ts=cycle_ts,
        # 직전 두 세션 + 당일. 사건 재판단의 subject 조회와 크리틱 급등락
        # 게이트(전일 종가)가 요구하는 최소 깊이다.
        bar_dates=(
            calendar.previous_trading_day(previous_session),
            previous_session,
            trade_date,
        ),
        broker_account_id=DEMO_ACCOUNT_ID,
        # 이어받기 모드에서는 운영 이력의 오늘 픽(RTX·AAPL 등)이 이 계좌에도
        # 배분된다. 10만이면 그 매수만으로 현금이 최소 유지선(평가액의 30%)
        # 아래로 내려가, 정작 각본 주인공(NVEX 호재 매수)이 min_cash로 막혔다.
        # 정책을 느슨하게 하는 대신 계좌를 키운다 — 문턱은 그대로 두고 각본이
        # 그 문턱 안에서 돌게 한다.
        opening_cash=Decimal("300000.00"),
        inv_type="aggressive",
        held=(
            HeldPosition(
                listing=DemoListing(
                    ticker=DEFENSE_TICKER, company=DEFENSE_COMPANY, sector="Tech"
                ),
                quantity=100,
                entry=Decimal("150.00"),
                stop=Decimal("139.50"),
                take=Decimal("172.50"),
            ),
            HeldPosition(
                listing=DemoListing(
                    ticker=BAD_TICKER, company=BAD_COMPANY, sector="Materials"
                ),
                quantity=200,
                entry=Decimal("80.00"),
                stop=Decimal("64.00"),
                take=Decimal("104.00"),
            ),
        ),
        candidates=(
            DemoListing(
                ticker=GOOD_TICKER,
                company=GOOD_COMPANY,
                sector="Tech",
                # 각본 감시 가격(55.00 고정)과 봉 기준가를 맞춘다 — 어긋나면
                # 매수 직후 방어선이 오발동한다(DemoListing.reference 주석).
                reference=Decimal("55.00"),
            ),
        ),
        users=(),  # 로그인은 seed CLI가 환경변수 비밀번호로 채운다.
        # 주인공은 픽 점수를 높게 받아 배분 줄의 맨 앞에 선다 — 이어받은
        # 운영 픽 수십 종목에 밀려 지갑이 빌 때까지 차례가 안 오는 것을 막는다.
        featured=frozenset({DEFENSE_TICKER, GOOD_TICKER, BAD_TICKER}),
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
            # 배경 종목도 값을 준다. 유니버스에 있는 이상 픽으로 올라올 수
            # 있고, 그때 각본에 가격이 없으면 감시 루프가 그 자리에서 죽는다.
            **{
                ticker: _flat(str(price), _FILM_MINUTES)
                for ticker, (_, price) in _background_listings().items()
            },
        },
        listings=_all_listings(),
        featured=frozenset({DEFENSE_TICKER, GOOD_TICKER, BAD_TICKER}),
        # 헤드라인은 라우팅의 결정론 키워드 필터(_HEADLINE_EVENT_TYPES)가
        # 인식하는 영어 마커를 포함해야 한다 — 각본이 운영 규칙에 맞춘다
        # (demo-video-plan.md §5). "guidance"가 두 기사 모두의 마커다.
        articles=scenario_articles(
            good=ScriptedHeadline(
                ticker=GOOD_TICKER,
                headline=(
                    f"{GOOD_COMPANY} raises full-year guidance "
                    "after landmark supply agreement"
                ),
                at=cycle_ts + timedelta(hours=1),
            ),
            bad=ScriptedHeadline(
                ticker=BAD_TICKER,
                headline=f"{BAD_COMPANY} withdraws full-year guidance on plant halt",
                at=cycle_ts + timedelta(hours=2),
            ),
        ),
        # 배경 수집물 — 전부 오늘의 분석 범위 밖이라 라우팅이 막는다.
        # 수집량은 늘리되 LLM 호출은 한 건도 만들지 않는다(demo/background.py).
        wire_articles=background_articles(published_from=session_start),
        filings=background_filings(trade_date=previous_session),
    )
