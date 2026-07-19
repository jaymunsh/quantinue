"""Typed input and output contracts for deterministic portfolio risk."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import floor
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantinue.orchestration.policy import ProfileConfig
from quantinue.roles.role_09_risk_portfolio.evidence import LateStageEvidenceInput

RISK_FRACTION: Final = 0.04
STOP_FRACTION: Final = 0.15
POSITION_CAP_FRACTION: Final = 0.25
TAKE_PROFIT_FRACTION: Final = 0.20


class RiskPortfolioInput(LateStageEvidenceInput):
    """Trusted inputs required by role 09's hard gates and sizing rule."""

    signal_id: int = Field(gt=0)
    account_id: int = Field(gt=0)
    ticker: str = Field(min_length=1, max_length=12)
    cycle_ts: datetime
    critic_approved: bool
    current_price: float = Field(ge=0.04)
    equity: float = Field(gt=0)
    has_position: bool = False
    has_open_order: bool = False
    event_within_two_days: bool = False
    daily_new_order_count: int = Field(default=0, ge=0)
    daily_new_order_cap: int = Field(default=5, ge=1)
    risk_score: float = Field(default=0, ge=0, le=1)
    reference_gap: float | None = Field(default=None, ge=0)
    """Absolute move from the analysis reference close, or None when unmeasured."""
    recent_return: float | None = None
    """Recent run-up as a fraction (0.15 = +15%), or None when unavailable."""
    cash: float | None = Field(default=None, ge=0)
    """Account cash available before this order, or None when unknown."""
    open_position_count: int = Field(default=0, ge=0)


class RiskPortfolioOutput(BaseModel):
    """Role 09 result, including observable skip decisions."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    signal_id: int
    account_id: int
    ticker: str
    decision: Literal["planned", "skipped"]
    quantity: int = Field(ge=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    skipped_reason: (
        Literal[
            "critic_rejected",
            "event_window",
            "existing_position",
            "open_order",
            "insufficient_equity",
            "daily_order_cap",
            "risk_limit",
            "premarket_gap",
            "late_entry",
            "max_positions",
            "min_cash",
        ]
        | None
    )
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_consistent_decision(self) -> "RiskPortfolioOutput":
        """Keep planned and skipped states mutually exclusive."""
        if not self.stop_loss < self.entry_price < self.take_profit:
            msg = "buy bracket must satisfy stop < entry < take-profit"
            raise ValueError(msg)
        is_planned = self.decision == "planned"
        if is_planned != (self.quantity > 0 and self.skipped_reason is None):
            msg = "planned requires positive quantity; skipped requires a reason"
            raise ValueError(msg)
        return self


def gap_guard_applies(now: datetime, session_open: datetime, open_minutes: int) -> bool:
    """Return whether the reference gap should be measured at this moment.

    The guard covers everything before the bell plus a short opening stretch,
    because that is where an overnight gap is a gap. Later in the session the
    same percentage is ordinary drift and blocking on it would skip normal buys.
    """
    return now < session_open + timedelta(minutes=open_minutes)


SkipReason = Literal[
    "critic_rejected",
    "event_window",
    "existing_position",
    "open_order",
    "insufficient_equity",
    "daily_order_cap",
    "risk_limit",
    "premarket_gap",
    "late_entry",
    "max_positions",
    "min_cash",
]


@dataclass(frozen=True, slots=True)
class PlanGates:
    """Thresholds applied before an order is sized."""

    maximum_risk_score: float = 1.0
    premarket_gap_max: float | None = None
    late_entry_max: float | None = None
    profile: ProfileConfig | None = None


def _blocking_reason(  # noqa: PLR0911 - a flat gate chain reads better than nesting
    request: RiskPortfolioInput, gates: PlanGates
) -> SkipReason | None:
    """Return the first hard gate that refuses this buy, in priority order."""
    profile = gates.profile
    if not request.critic_approved:
        return "critic_rejected"
    if request.risk_score > gates.maximum_risk_score:
        return "risk_limit"
    if (
        gates.premarket_gap_max is not None
        and request.reference_gap is not None
        and request.reference_gap > gates.premarket_gap_max
    ):
        # 기준가가 무너지면 진입가·손절·익절이 전부 무의미해진다.
        return "premarket_gap"
    if (
        gates.late_entry_max is not None
        and request.recent_return is not None
        and request.recent_return > gates.late_entry_max
    ):
        # 이미 달린 뒤에 올라타면 남은 상승분보다 손절까지의 거리가 길다.
        return "late_entry"
    if request.event_within_two_days:
        return "event_window"
    if request.has_position:
        return "existing_position"
    if request.has_open_order:
        return "open_order"
    if request.daily_new_order_count >= request.daily_new_order_cap:
        return "daily_order_cap"
    if profile is not None and request.open_position_count >= profile.max_positions:
        # 책이 가득 차면 확신도와 무관하게 새 종목을 받지 않는다.
        return "max_positions"
    return None


def build_order_plan(  # noqa: PLR0913 - one seam per gate threshold
    request: RiskPortfolioInput,
    stop_loss_ratio: float = STOP_FRACTION,
    take_profit_ratio: float = TAKE_PROFIT_FRACTION,
    maximum_risk_score: float = 1.0,
    premarket_gap_max: float | None = None,
    late_entry_max: float | None = None,
    profile: ProfileConfig | None = None,
) -> RiskPortfolioOutput:
    """Apply hard gates then size by risk budget subject to the weight cap."""
    reason: SkipReason | None = _blocking_reason(
        request,
        PlanGates(
            maximum_risk_score=maximum_risk_score,
            premarket_gap_max=premarket_gap_max,
            late_entry_max=late_entry_max,
            profile=profile,
        ),
    )
    weight_cap = profile.max_weight if profile is not None else POSITION_CAP_FRACTION
    risk_budget_allocation = request.equity * RISK_FRACTION / stop_loss_ratio
    capped_allocation = min(risk_budget_allocation, request.equity * weight_cap)
    quantity = floor(capped_allocation / request.current_price) if reason is None else 0
    if quantity > 0 and profile is not None and request.cash is not None:
        # 매수 뒤에도 현금 바닥이 유지되어야 한다 — 전액 투자는 금지.
        floor_cash = request.equity * profile.min_cash_ratio
        if request.cash - quantity * request.current_price < floor_cash:
            reason = "min_cash"
            quantity = 0
    if quantity == 0 and reason is None:
        reason = "insufficient_equity"
    return RiskPortfolioOutput(
        run_id=request.run_id,
        signal_id=request.signal_id,
        account_id=request.account_id,
        ticker=request.ticker,
        decision="planned" if quantity > 0 else "skipped",
        quantity=quantity,
        entry_price=request.current_price,
        stop_loss=round(request.current_price * (1 - stop_loss_ratio), 2),
        take_profit=round(request.current_price * (1 + take_profit_ratio), 2),
        skipped_reason=reason,
        evidence_ids=tuple(item.evidence_id for item in request.evidence),
    )
