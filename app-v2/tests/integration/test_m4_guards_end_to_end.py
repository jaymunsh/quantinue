"""Every M4 order-path guard fires through the real pipeline and store.

These guards were unverifiable by waiting: the critic rejects most candidates,
so a buy that reaches role 09/10 may not occur for days — and the day it does
is the day real money moves. Each guard is therefore forced deterministically.
"""

import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import ClassVar

import pytest

from quantinue.broker.mock import MockBroker
from quantinue.core.contracts import (
    PipelineContext,
    PipelineRequest,
    PipelineRun,
    PriceSnapshot,
)
from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.db.postgres import PostgresRunStore
from quantinue.llm.provider import DeterministicAnalyzer
from quantinue.orchestration.factory import build_roles
from quantinue.orchestration.pipeline import PipelineOrchestrator
from quantinue.orchestration.policy import GatesConfig, ProfileConfig
from quantinue.roles.role_02_technical_analysis.contracts import (
    TechnicalAnalysisOutput,
    TechnicalSnapshot,
    Trend,
)
from quantinue.roles.role_09_risk_portfolio.service import RiskPortfolio
from quantinue.roles.role_10_order_execution.service import OrderExecution

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")

# 2026-07-20 is a Monday. The bell rings at 13:30 UTC, so the gap-guard window
# closes at 14:00. Each test uses its own minute: the signal id is derived from
# (ticker, cycle_ts), and a shared one would make the order idempotency key
# collide so the first test's fill replays for every later one.
PREMARKET = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
PREMARKET_QUIET = datetime(2026, 7, 20, 12, 5, tzinfo=UTC)
MIDDAY = datetime(2026, 7, 20, 17, 0, tzinfo=UTC)
MIDDAY_LATE_ENTRY = datetime(2026, 7, 20, 17, 5, tzinfo=UTC)
MIDDAY_HALTED = datetime(2026, 7, 20, 17, 10, tzinfo=UTC)
GATES = GatesConfig()

# 다른 통합 테스트가 재사용하는 신선한 증거 한 건.
_EVIDENCE_FOR_PROFILE_TEST = Evidence(
    evidence_id="run-profile:08:critic",
    run_id="run-profile",
    source="critic",
    source_ref="policy://critic/v1",
    observed_at=MIDDAY,
    captured_at=MIDDAY,
    confidence=1.0,
    kind=EvidenceKind.MODEL_OUTPUT,
)


@dataclass(frozen=True, slots=True)
class _ConditionInjector:
    """Test-only role that sets up one guard condition after the real 01-08.

    Running the genuine upstream roles first is what makes this end to end:
    the strategist signal and account rows exist, so role 09/10 write against
    real foreign keys exactly as they do in production.
    """

    current: float = 100.0
    close_prev: float = 100.0
    ret_5d_percent: float = 0.0
    component: ClassVar[str] = "08"
    name: ClassVar[str] = "조건 주입"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Force a critic-approved buy carrying the condition under test."""
        snapshot = TechnicalSnapshot(
            trade_date=context.request.cycle_ts.date(),
            ticker=context.request.ticker,
            close=self.current,
            rs_20=1.0,
            vol_ratio=1.0,
            ret_5d=self.ret_5d_percent,
            ret_20d=1.0,
            atr_pct=1.0,
            high_252_ratio=1.0,
            rsi=50.0,
            macd=0.0,
            ma20=self.current,
            ma50=self.current,
            trend=Trend.UP,
            evidence_ids=(f"{context.run_id}:02:technical",),
        )
        return replace(
            context,
            last_price=self.current,
            critic_approved=True,
            price_snapshot=PriceSnapshot(
                current_price=self.current,
                day_high=max(self.current, self.close_prev),
                day_low=min(self.current, self.close_prev),
                close_prev=self.close_prev,
            ),
            technical_output=TechnicalAnalysisOutput(
                run_id=context.run_id, snapshots=(snapshot,)
            ),
        )


async def _run_guarded_pipeline(  # noqa: PLR0913 - one seam per guard condition
    cycle_ts: datetime,
    *,
    current: float = 100.0,
    close_prev: float = 100.0,
    ret_5d_percent: float = 0.0,
    halted: frozenset[str] = frozenset(),
    profile: ProfileConfig | None = None,
) -> PipelineRun:
    """Run 01-08 for real, inject one condition, then the real 09-11."""
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    broker = MockBroker(halted_tickers=halted)
    stock = build_roles(DeterministicAnalyzer(), broker, store=store)
    roles = (
        *stock[:8],
        _ConditionInjector(
            current=current, close_prev=close_prev, ret_5d_percent=ret_5d_percent
        ),
        RiskPortfolio(
            store=store,
            daily_new_order_cap=5,
            gates=GATES,
            profile=profile or ProfileConfig(),
        ),
        OrderExecution(broker, store),
        stock[10],
    )
    request = PipelineRequest(ticker="NVDA", cycle_ts=cycle_ts)
    return await PipelineOrchestrator(roles, store).run(request)


@pytest.mark.anyio
async def test_baseline_reaches_a_real_order_so_the_guards_are_meaningful() -> None:
    # Given: nothing wrong. This proves the harness genuinely buys, so a later
    # skip is caused by the guard rather than by an inert setup.
    result = await _run_guarded_pipeline(MIDDAY)

    assert result.order is not None
    assert result.order.status == "filled"


@pytest.mark.anyio
async def test_premarket_gap_stops_the_order_before_it_is_planned() -> None:
    # Given: analysis priced on a 100.00 close, reopening 8% higher pre-bell
    result = await _run_guarded_pipeline(PREMARKET, current=108.0, close_prev=100.0)

    assert result.order is None
    risk = next(stage for stage in result.stages if stage.component == "09")
    assert "갭" in risk.summary


@pytest.mark.anyio
async def test_late_entry_stops_a_stock_that_already_ran() -> None:
    # Given: +22% over five days, well past the aggressive 15% limit
    result = await _run_guarded_pipeline(MIDDAY_LATE_ENTRY, ret_5d_percent=22.0)

    assert result.order is None
    risk = next(stage for stage in result.stages if stage.component == "09")
    assert "5일 상승" in risk.summary


@pytest.mark.anyio
async def test_halted_symbol_never_reaches_the_broker() -> None:
    # Given: a plan that would otherwise submit, on a halted symbol
    result = await _run_guarded_pipeline(MIDDAY_HALTED, halted=frozenset({"NVDA"}))

    assert result.order is None
    execution = next(stage for stage in result.stages if stage.component == "10")
    assert "거래 불가" in execution.summary


@pytest.mark.anyio
async def test_a_quiet_reopen_inside_the_guard_window_still_buys() -> None:
    # The guard must not swallow ordinary premarket sessions.
    result = await _run_guarded_pipeline(PREMARKET_QUIET, current=100.5, close_prev=100.0)

    assert result.order is not None
