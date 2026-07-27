"""Demo runtime composition root: port 8022 + disposable DB 5490 only."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import yaml

from quantinue.core.config import (
    BrokerMode,
    DatabaseMode,
    DataMode,
    LlmMode,
    Settings,
)
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


def create_demo_app() -> FastAPI:
    """Assemble the filming app from scripted parts; run via uvicorn --factory.

    `.env`를 읽지 않는 것이 핵심이다(_env_file=None) — 운영 `.env`에는 실
    OpenAI 키·Telegram 토큰·5444 DB가 들어 있고, 그중 하나라도 새어 들면
    데모가 운영에 흔적을 남긴다. 데모 환경변수는 run_demo.sh가 전부 명시한다.
    """
    settings = Settings(_env_file=None)
    _require_demo_settings(settings)
    scenario = build_scenario()
    return create_app(
        settings,
        config=_demo_config(),
        llm_inner=ScenarioAnalyzer(stances=STANCES),
        job_sources=JobSources(
            # 각본 기사 2건 + 배경 수집물. 배경은 전부 분석 범위 밖이라
            # 라우팅에서 걸러지고 LLM은 한 번도 부르지 않는다 — 화면에는
            # "많이 모았고 관련된 것만 판단했다"가 남는다(demo/background.py).
            disclosures=ScriptedFilingProvider(filings=scenario.filings),
            news=ScriptedNewsProvider(articles=scenario.articles),
            wire_news=ScriptedNewsProvider(articles=scenario.wire_articles),
            ownership=_NoInsiders(),
        ),
        watch_quotes=ScriptedTradeSource(
            paths=scenario.price_paths,
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
