"""Job-shaped control room views — what today's pipeline actually did.

구 관제실은 "런 하나가 11단계를 어디까지 갔나"를 그렸다. 잡 기반에서는 그
질문이 성립하지 않는다 — 잡은 서로 독립이고 하나가 죽어도 나머지는 돈다.
그래서 화면의 질문도 바뀐다: **오늘 어떤 잡이 돌았고, 체인이 어디서
끊겼고, 그 결과 무엇을 샀고 왜 못 샀나.**

여기 있는 것은 전부 순수 함수다. 원장 레코드를 받아 화면 모델을 만들 뿐
DB를 모른다 — 화면 규칙(끊긴 지점 판정·스킵 사유 순위·변화율)을 DB 없이
테스트로 고정할 수 있어야 하기 때문이다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime  # noqa: TC003 - pydantic이 런타임에 해석한다
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field

from quantinue.core.ontology import Decision

if TYPE_CHECKING:
    from quantinue.db.control_room_reads import (
        AccountEquityPoint,
        ExitEventRecord,
        JobRunRecord,
        JudgementRecord,
        OrderPlanRecord,
    )

_RUNNING = "running"
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_PLANNED = "planned"
_SKIPPED = "skipped"
_PERCENT = Decimal(100)
_CENT = Decimal("0.01")
# 곡선 세로 축의 최소 폭(중앙값 대비). 이보다 작은 움직임은 화면에서도 작다.
_MIN_SPAN_RATIO = Decimal("0.02")


# 잡 이름은 **원장 키**라 바꿀 수 없다(tb_job_run의 PK 일부 — 바꾸면 지난
# 슬롯 이력이 끊긴다). 그래서 이름은 그대로 두고 화면에만 사람 말을 씌운다.
# 읽는 사람이 개발자가 아니어도 "무엇을 하는 단계인지" 알 수 있어야 한다.
_JOB_LABELS: Final[dict[str, str]] = {
    "universe": "종목 후보 수집",
    "daily_bars": "일별 시세 수집",
    "disclosures": "공시 수집",
    "news": "뉴스 수집",
    "news_wire": "보도자료 수집",
    "macro": "시장 국면 점검",
    "screening": "후보 압축",
    "insider_scoring": "내부자 거래 채점",
    "analysis:aggressive": "판단 · 공격형",
    "analysis:conservative": "판단 · 안전형",
    "exits": "보유 종목 청산 점검",
    "allocation": "매수 배분",
    # 원장의 실제 잡 이름은 benchmark_spy다 — "benchmark"로 적어 두는 바람에
    # 이 잡만 화면에서 한글 뜻 없이 영문 키로 떴다.
    "benchmark_spy": "지수(SPY) 수집",
    "review": "T+5 회고",
    "daily_summary": "일일 요약 알림",
}
_STATUS_LABELS: Final[dict[str, str]] = {
    "succeeded": "완료",
    "failed": "실패",
    "running": "진행 중",
}
# 성향은 계좌 화면·유저 화면에서 이미 "공격형/안전형"으로 부른다. 판단
# 패널만 원장 키(aggressive)를 그대로 제목에 걸고 있어 같은 것이 화면마다
# 다른 이름으로 보였다.
_INV_TYPE_LABELS: Final[dict[str, str]] = {
    "aggressive": "공격형",
    "conservative": "안전형",
}
# 매수가 막힌 이유. 원장에는 기계 코드로 남기고(집계·비교의 축) 화면에서만
# 사람 말로 바꾼다 — "왜 안 샀나"는 비개발자가 가장 먼저 묻는 질문이다.
# 키는 role 9의 SkipReason 리터럴과 같은 집합이어야 한다 — 여기 없는 코드는
# 화면에 영문 원문이 그대로 뜬다(실제로 min_cash가 그렇게 노출됐다).
_SKIP_LABELS: Final[dict[str, str]] = {
    "critic_rejected": "비평가 반려",
    "event_window": "사건 처리 중 보류",
    "existing_position": "이미 보유 중",
    "open_order": "미체결 주문 있음",
    "insufficient_equity": "계좌 평가액 부족",
    "daily_order_cap": "하루 주문 한도 도달",
    "risk_limit": "위험 점수 한도 초과",
    "premarket_gap": "개장 전 갭 과대",
    "late_entry": "추격 매수 구간",
    "max_positions": "보유 종목 수 한도",
    "min_cash": "최소 현금 유지선",
    # 아래는 과거 원장에 남아 있을 수 있는 구 코드다. 지우면 지난 슬롯을
    # 열었을 때 다시 영문이 노출된다.
    "not_tradable": "거래 불가 종목",
    "tradability_unavailable": "거래 가능 여부 확인 실패",
    "max_weight": "종목당 비중 한도",
    "min_cash_ratio": "최소 현금 비율 유지",
    "daily_loss_limit": "당일 손실 한도",
    "insufficient_cash": "현금 부족",
    "risk_off": "위험 회피 국면",
}


def skip_reason_label(reason: str) -> str:
    """Return the human phrase for one allocation skip code."""
    return _SKIP_LABELS.get(reason, reason)


class JobRunView(BaseModel):
    """One job's slot as the control room shows it."""

    model_config = ConfigDict(frozen=True)

    job_name: str
    status: str
    detail: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None = Field(default=None, ge=0)
    # 같은 슬롯의 시도 횟수. 재시도는 성공 뒤에 숨으므로 화면이 이 수를
    # 말하지 않으면 "한 번에 됐다"로 읽힌다.
    attempts: int = Field(default=1, ge=1)

    @property
    def display_name(self) -> str:
        """Return the ledger key with its meaning appended.

        이름을 **번역하지 않고 덧붙이는** 이유: 잡 이름은 로그·원장·문서에서
        그대로 쓰이는 공용 키라 화면에서만 다른 말로 부르면 대조가 끊긴다.
        그렇다고 영문 식별자만 두면 비개발자는 무슨 단계인지 모른다. 둘 다
        보여주면 개발자는 키로, 청중은 뜻으로 읽는다.
        """
        hint = _JOB_LABELS.get(self.job_name)
        return self.job_name if hint is None else f"{self.job_name} · {hint}"

    @property
    def status_label(self) -> str:
        """Return the Korean status word shown on the badge."""
        return _STATUS_LABELS.get(self.status, self.status)


class LlmSpendView(BaseModel):
    """Today's estimated LLM spend against its config ceiling.

    지출은 tb_llm_usage의 합(UTC 하루), 상한은 budget.daily_llm_usd다.
    원장이 없는 스토어에서는 이 뷰 자체가 None이다 — 0달러를 지어내 그리면
    "예산이 지켜지고 있다"는 거짓 신호가 된다.
    """

    model_config = ConfigDict(frozen=True)

    spent_usd: Decimal = Field(ge=0)
    limit_usd: Decimal = Field(ge=0)


class ChainView(BaseModel):
    """One day's job chain, in the order the runner executed it."""

    model_config = ConfigDict(frozen=True)

    slot_date: date | None
    jobs: tuple[JobRunView, ...] = ()
    succeeded: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    running: int = Field(default=0, ge=0)
    broke_at: str | None = None


class SkipReasonView(BaseModel):
    """How often one allocation gate blocked a buy today."""

    model_config = ConfigDict(frozen=True)

    reason: str
    count: int = Field(gt=0)

    @property
    def reason_label(self) -> str:
        """Return the human phrase shown beside the count."""
        return skip_reason_label(self.reason)


class OrderPlanView(BaseModel):
    """One allocation decision, bought or blocked."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    account_id: int | None
    decision: str
    skipped_reason: str | None
    quantity: int = Field(ge=0)
    entry_price: Decimal | None

    @property
    def skipped_reason_label(self) -> str | None:
        """Return the human phrase for this plan's skip code, if any."""
        if self.skipped_reason is None:
            return None
        return skip_reason_label(self.skipped_reason)


class AllocationView(BaseModel):
    """The day's allocation outcome with the reasons it stopped buying."""

    model_config = ConfigDict(frozen=True)

    bought: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    reasons: tuple[SkipReasonView, ...] = ()
    plans: tuple[OrderPlanView, ...] = ()

    # 화면은 산 것과 못 산 것을 다른 무게로 다룬다 — 매수는 몇 건이라 전부
    # 보여주고, 보류는 수백 건이라 접는다(이어받기 데모에서 503건이 그대로
    # 그려져 페이지가 3만 픽셀이 됐다). 필터를 템플릿이 아니라 여기 두는
    # 이유는 그 구분을 테스트로 고정하기 위해서다.
    @property
    def bought_plans(self) -> tuple[OrderPlanView, ...]:
        """Return only the plans that became orders."""
        return tuple(plan for plan in self.plans if plan.decision == _PLANNED)

    @property
    def skipped_plans(self) -> tuple[OrderPlanView, ...]:
        """Return only the plans a gate blocked."""
        return tuple(plan for plan in self.plans if plan.decision == _SKIPPED)


class EquityPointView(BaseModel):
    """One account's equity on one day."""

    model_config = ConfigDict(frozen=True)

    trade_date: date
    equity: Decimal


class AccountCurveView(BaseModel):
    """One account's recent equity curve and its move over the window."""

    model_config = ConfigDict(frozen=True)

    account_id: int
    # 원장이 이름을 못 주면(구 행) id로 부른다. 지어내지는 않는다.
    label: str
    points: tuple[EquityPointView, ...]
    opening_equity: Decimal
    latest_equity: Decimal
    change_pct: Decimal


class JudgementView(BaseModel):
    """One strategist judgement together with the critic's answer."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    side: str
    conviction: Decimal
    summary: str
    bull_case: str | None
    key_risk: str | None
    verdict_decision: str | None
    verdict_confidence: Decimal | None
    objection: str | None
    approved: bool


class ProfileJudgementsView(BaseModel):
    """One investment profile's judgements and how many survived the critic."""

    model_config = ConfigDict(frozen=True)

    inv_type: str
    total: int = Field(default=0, ge=0)
    approved: int = Field(default=0, ge=0)
    unjudged: int = Field(default=0, ge=0)
    judgements: tuple[JudgementView, ...] = ()

    @property
    def inv_type_label(self) -> str:
        """Return the Korean profile name shown as the block heading."""
        return _INV_TYPE_LABELS.get(self.inv_type, self.inv_type)


class WatchActivityView(BaseModel):
    """Durable evidence of intraday judgements, not a liveness claim."""

    model_config = ConfigDict(frozen=True)

    latest_at: datetime
    signal_count: int = Field(ge=0)
    ticker_count: int = Field(ge=0)


class ExitEventView(BaseModel):
    """A completed protective or judgement-driven close."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    account: str
    reason: str
    reason_label: str
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    filled_at: datetime


class PipelineDayView(BaseModel):
    """Everything the control room reports about one pipeline day."""

    model_config = ConfigDict(frozen=True)

    chain: ChainView
    allocation: AllocationView
    curves: tuple[AccountCurveView, ...] = ()
    profiles: tuple[ProfileJudgementsView, ...] = ()
    slots: tuple[date, ...] = ()
    # 지출 원장이 있는 스토어에서만 채워진다 — 없으면 카드를 그리지 않는다.
    llm: LlmSpendView | None = None
    watch: WatchActivityView | None = None
    exits: tuple[ExitEventView, ...] = ()


_EXIT_LABELS = {
    "stop": "손절",
    "take_profit": "익절",
    "time": "기간 청산",
    "thesis_break": "명제 붕괴",
    "thesis_soft": "판단 반전",
}


def exit_reason_label(reason: str) -> str | None:
    """Return the Korean rule name for one exit reason code, if known."""
    return _EXIT_LABELS.get(reason)


def exit_event_views(records: tuple[ExitEventRecord, ...]) -> tuple[ExitEventView, ...]:
    """Translate machine exit reasons without hiding unknown future values."""
    return tuple(
        ExitEventView(
            ticker=record.ticker,
            account=record.broker_account_id,
            reason=record.reason,
            reason_label=_EXIT_LABELS.get(record.reason, record.reason),
            quantity=record.quantity,
            price=record.price,
            filled_at=record.filled_at,
        )
        for record in records
    )


def _duration_ms(record: JobRunRecord) -> int | None:
    # 끝나지 않은 잡에 소요시간을 지어내지 않는다. 0이나 "지금까지 경과"를
    # 넣으면 화면에서 끝난 잡과 구별되지 않는다.
    if record.finished_at is None:
        return None
    elapsed = record.finished_at - record.started_at
    return max(int(elapsed.total_seconds() * 1000), 0)


def chain_view(slot_date: date | None, records: tuple[JobRunRecord, ...]) -> ChainView:
    """Project one day's job ledger rows into the chain panel.

    ``broke_at``은 **처음** 실패한 잡이다. 마지막이 아니라 처음인 이유는
    의존성이다 — 수집이 깨지면 그 뒤 판단 잡들도 줄줄이 실패하는데, 그때
    범인은 마지막에 실패한 잡이 아니라 체인을 끊은 첫 잡이다.
    """
    jobs = tuple(
        JobRunView(
            job_name=record.job_name,
            status=record.status,
            detail=record.detail,
            started_at=record.started_at,
            finished_at=record.finished_at,
            duration_ms=_duration_ms(record),
            attempts=record.attempts,
        )
        for record in records
    )
    statuses = Counter(job.status for job in jobs)
    broke_at = next((job.job_name for job in jobs if job.status == _FAILED), None)
    return ChainView(
        slot_date=slot_date,
        jobs=jobs,
        succeeded=statuses[_SUCCEEDED],
        failed=statuses[_FAILED],
        running=statuses[_RUNNING],
        broke_at=broke_at,
    )


def allocation_view(records: tuple[OrderPlanRecord, ...]) -> AllocationView:
    """Project the day's allocation decisions, ranking the blocks by frequency.

    스킵 사유를 빈도순으로 세우는 것은 문턱 조정의 입력이기 때문이다 —
    "무엇이 실제로 막고 있나"에 답하려면 목록이 아니라 순위가 필요하다.
    """
    plans = tuple(
        OrderPlanView(
            ticker=record.ticker,
            account_id=record.account_id,
            decision=record.decision,
            skipped_reason=record.skipped_reason,
            quantity=record.quantity,
            entry_price=record.entry_price,
        )
        for record in records
    )
    counted = Counter(
        plan.skipped_reason
        for plan in plans
        if plan.decision == _SKIPPED and plan.skipped_reason is not None
    )
    return AllocationView(
        bought=sum(1 for plan in plans if plan.decision == _PLANNED),
        skipped=sum(1 for plan in plans if plan.decision == _SKIPPED),
        reasons=tuple(
            SkipReasonView(reason=reason, count=count) for reason, count in counted.most_common()
        ),
        plans=plans,
    )


def equity_curve_views(points: tuple[AccountEquityPoint, ...]) -> tuple[AccountCurveView, ...]:
    """Group equity points into one curve per account, oldest point first."""
    grouped: dict[int, list[AccountEquityPoint]] = defaultdict(list)
    for point in points:
        grouped[point.account_id].append(point)
    curves: list[AccountCurveView] = []
    for account_id in sorted(grouped):
        series = sorted(grouped[account_id], key=lambda item: item.trade_date)
        opening = series[0].equity
        latest = series[-1].equity
        # 시작점이 0이면 변화율이 정의되지 않는다. 계좌 자본이 0인 상태는
        # 실제로 있을 수 있으므로(전액 손실) 나눗셈을 막고 0으로 보고한다.
        change = (
            ((latest - opening) / opening * _PERCENT).quantize(_CENT, rounding=ROUND_HALF_UP)
            if opening > 0
            else Decimal("0.00")
        )
        curves.append(
            AccountCurveView(
                account_id=account_id,
                label=series[0].broker_account_id or f"계좌 #{account_id}",
                points=tuple(
                    EquityPointView(trade_date=item.trade_date, equity=item.equity)
                    for item in series
                ),
                opening_equity=opening,
                latest_equity=latest,
                change_pct=change,
            )
        )
    return tuple(curves)


def sparkline_points(curve: AccountCurveView, *, width: int = 160, height: int = 32) -> str:
    """Return SVG polyline coordinates for one equity curve, or "" if unplottable.

    기하를 템플릿이 아니라 여기서 계산하는 이유는 테스트다 — 평평한 곡선의
    0으로 나누기나 점 하나짜리 계좌를 Jinja 안에서 고정할 방법이 없다.
    """
    return equity_sparkline([point.equity for point in curve.points], width=width, height=height)


def equity_sparkline(values: list[Decimal], *, width: int = 160, height: int = 32) -> str:
    """Return SVG polyline coordinates for a series of equity values.

    관제실 곡선과 유저 계좌 곡선이 **같은 기하**를 쓴다. 복사하면 한쪽만
    고쳐지는 날이 오고, 그때 같은 계좌가 두 화면에서 다른 모양으로 그려진다.
    """
    if len(values) < 2:  # noqa: PLR2004 - 점 하나로는 선분이 성립하지 않는다
        return ""
    low, high = min(values), max(values)
    # 세로 축에 **최소 폭**을 준다. min을 바닥에, max를 천장에 붙이는 정규화는
    # 변화의 크기를 지운다 — 실측으로 -0.01% 움직인 계좌가 절벽으로 그려졌다.
    # 하루치 유의미한 변동을 2%로 보고, 그보다 작은 움직임은 작게 보이게 한다.
    # 큰 변동(2% 초과)에는 아무 영향이 없다.
    midpoint = (low + high) / 2
    floor_span = abs(midpoint) * _MIN_SPAN_RATIO
    span = high - low
    if span < floor_span:
        low = midpoint - floor_span / 2
        span = floor_span
    step = Decimal(width) / Decimal(len(values) - 1)
    coordinates: list[str] = []
    for index, value in enumerate(values):
        # 완전히 평평한 구간(값이 0이라 최소 폭도 0인 경우 포함)은 중앙선으로
        # 그린다. 비율이 정의되지 않는데 바닥(0)에 붙이면 "전액 손실"로 읽힌다.
        ratio = Decimal("0.5") if span == 0 else (value - low) / span
        y_position = Decimal(height) - ratio * Decimal(height)
        coordinates.append(f"{index * step:.1f},{y_position:.1f}")
    return " ".join(coordinates)


def profile_judgement_views(
    records: tuple[JudgementRecord, ...],
) -> tuple[ProfileJudgementsView, ...]:
    """Split the day's judgements by investment profile, with approval counts.

    성향별로 가르는 이유는 그것이 이 시스템의 주장이기 때문이다 — 같은 증거로
    공격형과 안전형이 실제로 다르게 판단한다는 것. 합쳐서 보여주면 그 격차가
    화면에서 사라진다.

    승인 판정은 프로덕션 경로와 같은 어휘를 쓴다(``Decision.PASS``). 평결이
    없는 판단은 승인도 기각도 아니다 — 크리틱이 하지 않은 일을 뒤집어씌우면
    승인율 통계가 조용히 틀어진다.
    """
    grouped: dict[str, list[JudgementRecord]] = defaultdict(list)
    for record in records:
        grouped[record.inv_type].append(record)
    views: list[ProfileJudgementsView] = []
    for inv_type in sorted(grouped):
        items = grouped[inv_type]
        judgements = tuple(
            JudgementView(
                ticker=item.ticker,
                side=item.side,
                conviction=item.conviction,
                summary=item.summary,
                bull_case=item.bull_case,
                key_risk=item.key_risk,
                verdict_decision=item.verdict_decision,
                verdict_confidence=item.verdict_confidence,
                objection=item.objection,
                approved=item.verdict_decision == Decision.PASS,
            )
            for item in items
        )
        views.append(
            ProfileJudgementsView(
                inv_type=inv_type,
                total=len(judgements),
                approved=sum(1 for item in judgements if item.approved),
                unjudged=sum(1 for item in judgements if item.verdict_decision is None),
                judgements=judgements,
            )
        )
    return tuple(views)
