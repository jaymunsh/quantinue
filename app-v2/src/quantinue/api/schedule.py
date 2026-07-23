"""The operating basis: when jobs run, on whose clock, and why.

관제실이 "오늘 무슨 일이 있었나"를 답한다면, 이 화면은 그 앞의 질문에
답한다 — **애초에 언제 돌기로 되어 있나.** 지금까지 그 답은 코드와
``pipeline.yaml``에만 있었고 화면만 보고는 알 수 없었다.

세 가지가 한 화면에 있어야 답이 된다:

1. **시계** — 슬롯은 뉴욕 날짜다. 뉴욕 자정(서울 13:00)에 "오늘"이 바뀐다.
2. **주기** — 요일 고정이 아니라 **마지막 성공으로부터 경과일**이다(D3).
   그래서 꺼져 있던 날은 건너뛰는 게 아니라 다음에 켤 때 뒤늦게 돈다.
3. **순서** — 등록 순서가 곧 실행 순서이고 데이터 의존성이다.

다음 예정일은 실행 판정과 **같은 술어**(``is_job_due``)로 센다. 화면이 따로
계산하면 "화면은 오늘이라는데 안 돈다"가 생긴다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

from quantinue.core.market_calendar import NEW_YORK, NyseCalendar
from quantinue.orchestration.job_cadence import is_job_due
from quantinue.runtime_status import RuntimeSnapshot, RuntimeView, present_runtime

if TYPE_CHECKING:
    from quantinue.orchestration.policy import JobsConfig

# 잡 이름 → 사람이 읽는 한 줄. 정책이 아니라 화면 문구라 여기 산다.
# 등록되지 않은 이름은 그대로 보여준다 — 지어내지 않는다.
JOB_SUMMARIES: dict[str, str] = {
    "universe": "거래 가능 종목 목록을 새로 뜬다 (시총 상위 2,000 + 보유 전부)",
    "daily_bars": "일봉을 채운다. 빠진 구간은 자동으로 소급 수집한다",
    "disclosures": "SEC 공시를 전 시장 하루치 받는다",
    "news": "헤드라인을 전 시장에서 받는다 (투표권 없음, 판단의 맥락)",
    "news_wire": "보도자료 RSS(GNW·PRN)를 받는다",
    "macro": "금리에서 시장 국면을 판정한다",
    "screening": "원장만 보고 오늘 깊이 볼 종목을 고른다 (API 0콜)",
    "insider_scoring": "Form 4의 재량 거래를 표로 만든다",
    "analysis:aggressive": "공격형이 종목마다 판단하고 크리틱이 반박한다",
    "analysis:conservative": "안전형이 종목마다 판단하고 크리틱이 반박한다",
    "exits": "손절·익절·시간·매도판단으로 보유를 청산한다",
    "allocation": "승인된 후보를 지갑이 허락할 때까지 산다",
    "daily_summary": "그날의 결과를 텔레그램으로 한 통 보낸다",
}


class ScheduleLedger(Protocol):
    """The one ledger read this page needs."""

    async def last_job_success(self, job_name: str) -> date | None:
        """Return the last slot this job completed, if any."""
        ...


class ScheduledJobView(BaseModel):
    """One registered job and when it next runs."""

    model_config = ConfigDict(frozen=True)

    order: int = Field(ge=1)
    job_name: str
    summary: str
    interval_days: int = Field(ge=1)
    enabled: bool
    last_success: date | None
    next_due: date | None
    due_today: bool


class ScheduleView(BaseModel):
    """The operating basis as one screen."""

    model_config = ConfigDict(frozen=True)

    slot_date: date
    is_trading_day: bool
    jobs_enabled: bool
    tick_seconds: int = Field(ge=1)
    runtime: RuntimeView
    jobs: tuple[ScheduledJobView, ...] = ()


def _next_due(last_success: date | None, slot: date, interval_days: int) -> date | None:
    """Return the first slot this job becomes due on.

    한 번도 안 돈 잡은 지금이 그 날이다. 그 외에는 마지막 성공 + 주기인데,
    이미 지난 날짜면 오늘로 당긴다 — 밀린 잡은 과거가 아니라 지금 돈다.
    """
    if last_success is None:
        return slot
    return max(last_success + timedelta(days=interval_days), slot)


async def build_schedule(  # noqa: PLR0913 - presentation needs policy, ledger, clock and runtime
    *,
    job_names: tuple[str, ...],
    config: JobsConfig,
    ledger: ScheduleLedger,
    now: datetime,
    runtime: RuntimeSnapshot | None = None,
    calendar: NyseCalendar | None = None,
) -> ScheduleView:
    """Project the registered jobs into their operating basis."""
    market = calendar or NyseCalendar()
    # 슬롯은 뉴욕 세션일이다 — 러너와 같은 계산이라야 화면이 거짓말하지 않는다.
    slot = now.astimezone(NEW_YORK).date()
    jobs: list[ScheduledJobView] = []
    for index, name in enumerate(job_names, start=1):
        cadence = config.cadence_for(name)
        last_success = await ledger.last_job_success(name)
        jobs.append(
            ScheduledJobView(
                order=index,
                job_name=name,
                summary=JOB_SUMMARIES.get(name, "—"),
                interval_days=cadence.interval_days,
                enabled=cadence.enabled,
                last_success=last_success,
                next_due=_next_due(last_success, slot, cadence.interval_days),
                due_today=cadence.enabled
                and is_job_due(
                    last_success=last_success,
                    as_of=slot,
                    interval_days=cadence.interval_days,
                ),
            )
        )
    return ScheduleView(
        slot_date=slot,
        is_trading_day=market.is_trading_day(slot),
        jobs_enabled=config.enabled,
        tick_seconds=config.tick_seconds,
        runtime=present_runtime(
            runtime
            or RuntimeSnapshot.web_only(
                rejudge_configured=False,
                stream_configured=False,
            ),
            now=now,
            calendar=market,
        ),
        jobs=tuple(jobs),
    )
