"""The operations log view: many days at a glance, from the job ledger alone.

관제실(`pipeline_day`)이 슬롯 하나를 깊게 본다면, 이 뷰는 여러 날을 한 화면에
펼친다 — "매일 돌았나, 몇 번 돌았나, 안내는 나갔나"가 질문이다. 숫자는 전부
``tb_job_run``이 답할 수 있는 것만 싣는다: 시도 횟수는 ``attempts`` 컬럼이,
안내 발송은 ``daily_summary`` 잡의 성공 행이 근거다.
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - pydantic이 런타임에 필드 타입을 해석한다
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from quantinue.db.control_room_reads import JobRunRecord

# 한 쪽에 펼치는 날 수. 표시용 창이라 config가 아니라 여기 산다 —
# 어떤 매매 결정에도 들어가지 않는다.
DEFAULT_PER_PAGE = 10
# 원장에서 가져올 슬롯의 상한. 하루 한 행씩 늘어 10년치라도 수천 행이므로
# 전부 읽어 세는 편이 쪽수를 위해 따로 세는 것보다 단순하고 정직하다.
_MAX_SLOTS = 3650

# 일일 안내 잡의 원장 이름. 이 행의 성공이 곧 "그날 안내가 나갔다"다.
_SUMMARY_JOB = "daily_summary"


class OpsLogReads(Protocol):
    """The two ledger reads this page needs."""

    async def recent_job_slots(self, *, limit: int) -> tuple[date, ...]:
        """Return the days the runner touched, newest first."""
        ...

    async def job_runs(self, slot_date: date) -> tuple[JobRunRecord, ...]:
        """List one day's job chain in execution order."""
        ...


class OpsLogJobView(BaseModel):
    """One job's row in the log."""

    model_config = ConfigDict(frozen=True)

    job_name: str
    status: str
    attempts: int = Field(ge=1)
    detail: str | None
    started_at: datetime
    duration_ms: int | None = Field(default=None, ge=0)


class OpsLogSlotView(BaseModel):
    """One day's verdict: did the chain run, how many times, was it announced."""

    model_config = ConfigDict(frozen=True)

    slot_date: date
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    running: int = Field(ge=0)
    # 재시도가 있었던 잡 수(attempts > 1). "하루에 여러 번 돌았다"의 원장 표현.
    retried_jobs: int = Field(ge=0)
    summary_sent: bool = False
    jobs: tuple[OpsLogJobView, ...] = ()


class OpsLogView(BaseModel):
    """One page of the log, newest day first."""

    model_config = ConfigDict(frozen=True)

    slots: tuple[OpsLogSlotView, ...] = ()
    # 쪽 나누기. "최근 며칠"이 아니라 **전부**를 보여주되 한 화면에 쏟지 않는다 —
    # 며칠치인지가 화면에 따라 달라지면 "빠진 날이 있나"를 물을 수 없다.
    page: int = Field(default=1, ge=1)
    total_pages: int = Field(default=1, ge=1)
    total_slots: int = Field(default=0, ge=0)
    per_page: int = Field(default=DEFAULT_PER_PAGE, ge=1)

    @property
    def first_index(self) -> int:
        """1-based index of this page's newest slot, for the header."""
        return (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        """1-based index of this page's oldest slot."""
        return self.first_index + len(self.slots) - 1


def _job_view(record: JobRunRecord) -> OpsLogJobView:
    duration_ms = None
    if record.finished_at is not None:
        duration_ms = max(
            0, int((record.finished_at - record.started_at).total_seconds() * 1000)
        )
    return OpsLogJobView(
        job_name=record.job_name,
        status=record.status,
        attempts=record.attempts,
        detail=record.detail,
        started_at=record.started_at,
        duration_ms=duration_ms,
    )


def _slot_view(slot: date, records: tuple[JobRunRecord, ...]) -> OpsLogSlotView:
    return OpsLogSlotView(
        slot_date=slot,
        total=len(records),
        succeeded=sum(1 for item in records if item.status == "succeeded"),
        failed=sum(1 for item in records if item.status == "failed"),
        running=sum(1 for item in records if item.status == "running"),
        retried_jobs=sum(1 for item in records if item.attempts > 1),
        summary_sent=any(
            item.job_name == _SUMMARY_JOB and item.status == "succeeded"
            for item in records
        ),
        jobs=tuple(_job_view(item) for item in records),
    )


async def build_ops_log(
    reads: OpsLogReads,
    *,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
) -> OpsLogView:
    """Project one page of slots into the log, newest first.

    범위 밖 쪽수는 마지막 쪽으로 당긴다. URL을 손으로 고쳤을 때 빈 화면을
    보여주면 "기록이 없다"로 읽히는데, 사실은 그 쪽이 없는 것뿐이다.

    잡 상세는 **이 쪽의 날짜만** 읽는다 — 슬롯 목록은 한 번의 조회지만
    상세는 날짜마다 한 번이라, 전부 읽으면 쪽 나누기가 의미를 잃는다.
    """
    all_slots = await reads.recent_job_slots(limit=_MAX_SLOTS)
    total = len(all_slots)
    total_pages = max(1, -(-total // per_page))
    current = min(max(page, 1), total_pages)
    window = all_slots[(current - 1) * per_page : current * per_page]
    return OpsLogView(
        slots=tuple([_slot_view(slot, await reads.job_runs(slot)) for slot in window]),
        page=current,
        total_pages=total_pages,
        total_slots=total,
        per_page=per_page,
    )
