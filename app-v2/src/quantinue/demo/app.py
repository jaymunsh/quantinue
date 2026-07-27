"""Demo runtime composition root: port 8022 + disposable DB 5490 only."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import yaml

from quantinue.core.config import (
    BrokerMode,
    DatabaseMode,
    DataMode,
    LlmMode,
    Settings,
)
from quantinue.db.postgres import PostgresRunStore
from quantinue.demo.market import DemoMarketData
from quantinue.demo.scenario import STANCES, build_scenario
from quantinue.demo.scenario_analyzer import ScenarioAnalyzer
from quantinue.demo.scripted_events import (
    ScriptedFilingProvider,
    ScriptedNewsProvider,
)
from quantinue.demo.scripted_market import (
    DemoScenarioError,
    ScriptedTradeSource,
    SteppingClock,
)
from quantinue.main import PACKAGE_DIR, create_app
from quantinue.orchestration.job_factory import JobSources
from quantinue.orchestration.policy import Mvp2Config

if TYPE_CHECKING:
    from fastapi import FastAPI

    from quantinue.market_data.sec_ownership import InsiderTransaction

_DEMO_DB_MARKER = ":5490/"
# 이어받은 보유의 평탄 시세 길이 — 각본(_FILM_MINUTES)과 같은 촬영 여유.
_INHERITED_PATH_LENGTH = 240


class _NoInsiders:
    """Silent Form 4 stand-in for the same reason as `_NoFilings`."""

    async def transactions(
        self, source_refs: tuple[str, ...]
    ) -> tuple[InsiderTransaction, ...]:
        _ = source_refs
        return ()


def _require_demo_settings(settings: Settings) -> None:
    """Refuse to assemble anything that could reach production state.

    demo-video-plan.md §4-4 완료 기준: 5444·5445·5480을 지정하면 연결 전에
    거부한다. 여기서는 더 좁게 "5490이 아니면 전부 거부"로 닫는다 — 허용
    목록이 금지 목록보다 새 구멍에 강하다.
    """
    url = str(settings.database_url)
    if _DEMO_DB_MARKER not in url:
        msg = f"demo runtime requires the disposable DB on 5490, got {url}"
        raise DemoScenarioError(msg)
    if settings.database_mode is not DatabaseMode.POSTGRES:
        msg = "demo runtime requires database_mode=postgres"
        raise DemoScenarioError(msg)
    if settings.llm_mode is not LlmMode.MOCK:
        msg = "demo runtime refuses paid LLM modes; use llm_mode=mock"
        raise DemoScenarioError(msg)
    if settings.broker_mode is not BrokerMode.MOCK:
        msg = "demo runtime refuses real broker modes"
        raise DemoScenarioError(msg)
    if settings.data_mode is not DataMode.FIXTURE:
        msg = "demo runtime refuses live market data; use data_mode=fixture"
        raise DemoScenarioError(msg)
    if not settings.background_workers:
        msg = "demo runtime needs background_workers=1 to film the watch loop"
        raise DemoScenarioError(msg)


def _demo_config() -> Mvp2Config:
    """Load the production pipeline config with the demo overlay applied.

    파일을 복사하지 않고 메모리에서 덮는다 — 운영 `pipeline.yaml`은 불변이
    금지선이고, 사본 파일은 원본과 조용히 어긋난다. 덮는 키는 rejudge 활성
    단 하나다: 문턱·쿨다운·스윕 시각 등 운영값은 각본이 맞춰야 할 상수다.
    """
    path = PACKAGE_DIR.parent.parent / "config" / "pipeline.yaml"
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream) or {}
    mvp2 = document.get("mvp2") or {}
    mvp2["watch"]["rejudge"]["enabled"] = True
    return Mvp2Config.model_validate(mvp2)


async def _inherited_position_prices(
    database_url: str, *, known: frozenset[str]
) -> dict[str, Decimal]:
    """Give inherited holdings a quiet flat price so the watch loop can run.

    운영 원장을 복사해 이어받는 모드(--with-history)에서는 각본에 없는 실보유
    종목이 감시 대상에 들어온다. 각본 시세는 미등록 티커에 즉시 실패하므로,
    이어받은 보유에는 "마지막 종가에 멈춘" 평탄한 시세를 준다 — 방어선을
    새로 발동시키지도, 5% 트리거를 건드리지도 않는 값이다. 종가가 이미
    손절선 아래면 손절선 위로 살짝 올려 잡는다: 이어받은 화면에서 각본에
    없는 청산이 터지면 촬영 장면이 회차마다 달라진다.
    """
    store = PostgresRunStore(database_url)
    await store.initialize()
    try:
        domain = store.domain
        positions = await domain.open_positions()
        # 보유만으로는 부족하다 — 운영이 오늘 이미 돌았으면 오늘 날짜의 실제
        # 후보(픽)까지 복사돼 와서 감시 대상에 들어온다(실측: AAPL로 tick이
        # 죽었다). 감시가 물어볼 전체 집합에 값을 준다.
        today = datetime.now(UTC).date()
        watched = await domain.watch_tickers(today)
        inherited = tuple(({p.ticker for p in positions} | set(watched)) - known)
        if not inherited:
            return {}
        closes = await domain.reference_closes(
            inherited, before=today + timedelta(days=1)
        )
        stops = {
            p.ticker: p.stop_price for p in positions if p.stop_price is not None
        }
        prices: dict[str, Decimal] = {}
        for ticker in inherited:
            price = closes.get(ticker, Decimal("100.00"))
            stop = stops.get(ticker)
            if stop is not None and price <= stop:
                price = stop * Decimal("1.02")
            # 실봉 종가는 소수 셋째 자리가 흔하다(212.855 실측). 주문·체결
            # 경로는 센트 단위 계약이라 그대로 흘리면 pydantic이 거부한다.
            prices[ticker] = price.quantize(Decimal("0.01"))
        return prices
    finally:
        await store.close()


def create_demo_app() -> FastAPI:
    """Assemble the filming app from scripted parts; run via uvicorn --factory.

    `.env`를 읽지 않는 것이 핵심이다(_env_file=None) — 운영 `.env`에는 실
    OpenAI 키·Telegram 토큰·5444 DB가 들어 있고, 그중 하나라도 새어 들면
    데모가 운영에 흔적을 남긴다. 데모 환경변수는 run_demo.sh가 전부 명시한다.
    """
    settings = Settings(_env_file=None)
    _require_demo_settings(settings)
    scenario = build_scenario()
    market = DemoMarketData(
        listings=scenario.listings, featured=scenario.featured
    )
    # uvicorn --factory는 이 함수를 **돌고 있는 이벤트 루프 안에서** 부른다
    # (실측 — asyncio.run이 RuntimeError로 죽었다). 그래서 별도 스레드의
    # 새 루프에서 한 번 읽는다. 부팅 시 1회뿐이라 스레드 비용은 무시된다.
    price_paths = dict(scenario.price_paths)
    with ThreadPoolExecutor(max_workers=1) as executor:
        inherited = executor.submit(
            asyncio.run,
            _inherited_position_prices(
                str(settings.database_url), known=frozenset(price_paths)
            ),
        ).result()
    for ticker, price in inherited.items():
        price_paths[ticker] = (price,) * _INHERITED_PATH_LENGTH
    return create_app(
        settings,
        config=_demo_config(),
        llm_inner=ScenarioAnalyzer(stances=STANCES),
        job_sources=JobSources(
            # 시세·유니버스·매크로를 물려야 universe·daily_bars·benchmark·
            # macro 잡이 등록된다. 없으면 관제실이 잡 9개만 보여주는데 실제
            # 시스템은 13개다 — 화면이 시스템을 축소해 보여주면 안 된다.
            market_data=market,
            bars=market,
            macro=market,
            # 각본 기사 2건 + 배경 수집물. 배경은 전부 분석 범위 밖이라
            # 라우팅에서 걸러지고 LLM은 한 번도 부르지 않는다 — 화면에는
            # "많이 모았고 관련된 것만 판단했다"가 남는다(demo/background.py).
            disclosures=ScriptedFilingProvider(filings=scenario.filings),
            news=ScriptedNewsProvider(articles=scenario.articles),
            wire_news=ScriptedNewsProvider(articles=scenario.wire_articles),
            ownership=_NoInsiders(),
        ),
        watch_quotes=ScriptedTradeSource(
            paths=price_paths,
            clock=SteppingClock(
                start=scenario.session_start + timedelta(minutes=30),
                step=timedelta(minutes=1),
            ),
        ),
        # 러너 시계는 1초 걸음이다: 한 tick 안에서 여러 번 읽혀도 정규장
        # 밖으로 걸어 나가지 않는다(6.5시간 = 23,400걸음). 감시와 잡 루프가
        # 시계 인스턴스를 공유하면 두 비동기 루프의 교차가 걸음 수를 비결정으로
        # 만들므로 각자 하나씩 갖는다.
        watch_clock=SteppingClock(
            start=scenario.session_start + timedelta(minutes=30),
            step=timedelta(seconds=1),
        ),
        job_clock=SteppingClock(
            start=scenario.session_start + timedelta(minutes=30),
            step=timedelta(seconds=1),
        ),
    )
