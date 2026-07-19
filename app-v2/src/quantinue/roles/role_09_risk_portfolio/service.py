"""Create a deterministic risk-sized fixed-bracket order plan."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from hashlib import sha256
from typing import ClassVar, assert_never

from exchange_calendars.errors import DateOutOfBounds

from quantinue.core.contracts import PipelineContext
from quantinue.core.market_calendar import NyseCalendar
from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.core.typing import require_value
from quantinue.db.contracts import (
    AppOrderExposureReservationOutcome,
    DailyOrderReservation,
    RunStore,
    parse_app_order_money,
)
from quantinue.db.domain_records import AccountRiskState
from quantinue.orchestration.policy import GatesConfig, ProfileConfig
from quantinue.roles.role_09_risk_portfolio.contracts import (
    RiskPortfolioInput,
    build_order_plan,
    gap_guard_applies,
)
from quantinue.roles.role_09_risk_portfolio.evidence import evidence_from_pipeline_traces


@dataclass(frozen=True, slots=True)
class RiskPortfolio:
    """Deterministic risk gate between LLM output and broker submission."""

    component: ClassVar[str] = "09"
    name: ClassVar[str] = "리스크·포트폴리오"
    store: RunStore
    daily_new_order_cap: int = 1
    max_app_order_exposure_usd: Decimal = Decimal("1000.00")
    maximum_risk_score: float = 1.0
    stop_loss_ratio: float = 0.15
    take_profit_ratio: float = 0.20
    gates: GatesConfig = field(default_factory=GatesConfig)
    calendar: NyseCalendar = field(default_factory=NyseCalendar)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    profiles: Mapping[str, ProfileConfig] = field(default_factory=dict)

    def _profile_for(self, inv_type: str | None) -> ProfileConfig:
        """Pick the profile the account actually subscribes to."""
        if inv_type is None:
            return self.profile
        return self.profiles.get(inv_type, self.profile)

    async def _account_state(self, account_id: int) -> AccountRiskState | None:
        """Read this account's capital and book, when the store can answer."""
        reader = getattr(self.store, "account_risk_state", None)
        if reader is None:
            return None
        return await reader(account_id)

    def _recent_return(self, context: PipelineContext) -> float | None:
        """Return role 02's five-day run-up as a fraction.

        role 02 reports `ret_5d` in percent; the profile threshold is a
        fraction. Normalising here keeps the unit conversion in one place
        instead of leaving a silent 100x mismatch at the comparison.
        """
        output = context.technical_output
        if output is None:
            return None
        ticker = context.request.ticker
        snapshot = next((item for item in output.snapshots if item.ticker == ticker), None)
        if snapshot is None:
            return None
        return snapshot.ret_5d / 100

    def _reference_gap(self, context: PipelineContext) -> float | None:
        """Measure the gap from the analysis reference close, inside the window only.

        Returns None when the guard does not apply, so a plain drift later in
        the session is never mistaken for an overnight gap.
        """
        snapshot = context.price_snapshot
        if snapshot is None:
            return None
        now = context.request.cycle_ts
        try:
            if not self.calendar.is_trading_day(now.date()):
                return None
            session_open = self.calendar.session_open(now.date())
        except (ValueError, DateOutOfBounds):
            # 거래소 캘린더는 유한한 구간만 안다. 그 밖의 날짜라면 세션을 판정할 수
            # 없으니 측정하지 않는다 — 가드가 파이프라인을 죽이는 쪽이 더 나쁘다.
            return None
        if not gap_guard_applies(now, session_open, self.gates.gap_guard_open_minutes):
            return None
        return snapshot.gap_from_reference()

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply role 09's hard gates and risk-budget sizing formula."""
        price = require_value(context.last_price, component=self.component, field_name="last_price")
        signal_key = f"{context.request.ticker}:{context.request.cycle_ts.isoformat()}".encode()
        signal_id = context.signal_id or int(sha256(signal_key).hexdigest()[:8], 16) + 1
        account_id = context.account_id or 1
        state = await self._account_state(account_id)
        profile = self._profile_for(state.inv_type if state is not None else None)
        # 자본은 계좌에서 온다. 앱 전역 노출 상한을 자본으로 쓰면 $5,000 계좌와
        # $150,000 계좌가 같은 크기로 주문한다.
        equity = (
            float(state.equity) if state is not None else float(self.max_app_order_exposure_usd)
        )
        plan = build_order_plan(
            RiskPortfolioInput(
                run_id=context.run_id,
                execution_at=context.request.cycle_ts,
                evidence=evidence_from_pipeline_traces(context, ("08",)),
                signal_id=signal_id,
                account_id=account_id,
                ticker=context.request.ticker,
                cycle_ts=context.request.cycle_ts,
                critic_approved=context.critic_approved,
                current_price=price,
                equity=equity,
                cash=float(state.cash) if state is not None else None,
                open_position_count=state.open_position_count if state is not None else 0,
                daily_new_order_cap=self.daily_new_order_cap,
                risk_score=context.macro_risk_score or 0,
                reference_gap=self._reference_gap(context),
                recent_return=self._recent_return(context),
            ),
            stop_loss_ratio=self.stop_loss_ratio,
            take_profit_ratio=self.take_profit_ratio,
            maximum_risk_score=self.maximum_risk_score,
            premarket_gap_max=self.gates.premarket_gap_max,
            late_entry_max=profile.late_entry_max,
            profile=profile,
        )
        if plan.quantity > 0:
            reserved = await self.store.reserve_daily_new_order(
                DailyOrderReservation(
                    account_id=plan.account_id,
                    trade_date=context.request.cycle_ts.date(),
                    signal_id=plan.signal_id,
                    idempotency_key=f"q-a{plan.account_id}-s{plan.signal_id}",
                    ticker=plan.ticker,
                    quantity=plan.quantity,
                    entry_price=parse_app_order_money(plan.entry_price),
                    stop_price=parse_app_order_money(plan.stop_loss),
                    take_profit_price=parse_app_order_money(plan.take_profit),
                    cap=self.daily_new_order_cap,
                    max_app_order_exposure_usd=self.max_app_order_exposure_usd,
                )
            )
            match reserved.outcome:
                case (
                    AppOrderExposureReservationOutcome.ACQUIRED
                    | AppOrderExposureReservationOutcome.REPLAYED
                ):
                    pass
                case AppOrderExposureReservationOutcome.REJECTED:
                    plan = plan.model_copy(
                        update={
                            "decision": "skipped",
                            "quantity": 0,
                            "skipped_reason": "daily_order_cap",
                        }
                    )
                case unreachable:
                    assert_never(unreachable)
        summary = f"수량={plan.quantity} · 손절={plan.stop_loss} · 익절\u00a0{plan.take_profit}"
        if plan.quantity == 0:
            summary = f"주문 보류 · {summary}"
        if plan.quantity == 0 and plan.skipped_reason == "daily_order_cap":
            summary = "수량 0, 앱 주문 계획 노출 한도 또는 일일 신규 주문 한도 도달"
        if plan.skipped_reason == "late_entry":
            run_up = self._recent_return(context) or 0.0
            summary = f"주문 보류 · 5일 상승 {run_up:.1%} > {profile.late_entry_max:.1%}"
        if plan.skipped_reason == "max_positions":
            summary = f"주문 보류 · 보유 종목 수 한도 {profile.max_positions}개 도달"
        if plan.skipped_reason == "min_cash":
            summary = f"주문 보류 · 현금 바닥 {profile.min_cash_ratio:.0%} 유지"
        if plan.skipped_reason == "premarket_gap":
            gap = self._reference_gap(context) or 0.0
            summary = f"주문 보류 · 기준가 대비 갭 {gap:.1%} > {self.gates.premarket_gap_max:.1%}"
        updated = replace(
            context,
            signal_id=plan.signal_id,
            account_id=plan.account_id,
            quantity=plan.quantity,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            risk_decision=plan.decision,
            risk_skipped_reason=plan.skipped_reason,
            risk_entry_price=plan.entry_price,
        )
        evidence = Evidence(
            evidence_id=f"{context.run_id}:09:risk-plan",
            run_id=context.run_id,
            source="risk-policy-code",
            source_ref="policy://risk-portfolio/v1",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.MODEL_OUTPUT,
            parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
        )
        return updated.add_stage(
            self.component,
            self.name,
            summary,
            evidence=evidence,
        )
