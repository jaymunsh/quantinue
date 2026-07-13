from dataclasses import replace
from datetime import UTC, datetime
from typing import ClassVar

import pytest

from quantinue.core.contracts import (
    DisclosureSourceRecord,
    PipelineContext,
    PipelineRequest,
)
from quantinue.db.store import InMemoryRunStore
from quantinue.llm.provider import DeterministicAnalyzer
from quantinue.orchestration.factory import build_default_orchestrator
from quantinue.orchestration.pipeline import PipelineOrchestrator
from quantinue.roles.role_07_strategist.contracts import StrategyInput, StrategyOutput
from quantinue.roles.role_08_critic.service import Critic

NOW = datetime(2026, 7, 13, 13, 0, tzinfo=UTC)


class _CollectedDetailRole:
    component: ClassVar[str] = "01"
    name: ClassVar[str] = "collect detail"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        collected = replace(
            context,
            disclosure_score=0.78,
            disclosure_source=DisclosureSourceRecord(
                filing_no="filing-1",
                title="Collected filing",
                form_type="8-K",
                filed_at=NOW,
                event_type="other",
                source_ref="sec://filing/filing-1",
                summary="A collected summary.",
            ),
        )
        return collected.add_stage(self.component, self.name, "done")


class _FailingAfterDetailRole:
    component: ClassVar[str] = "02"
    name: ClassVar[str] = "fail after detail"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        del context
        msg = "fixture failure"
        raise RuntimeError(msg)


@pytest.mark.anyio
async def test_pipeline_run_retains_safe_collection_strategy_and_critic_detail() -> None:
    # Given
    request = PipelineRequest(ticker="NVDA", cycle_ts=NOW)

    # When
    run = await build_default_orchestrator().run(request)

    # Then
    assert run.detail.disclosure.title == "Deterministic fixture filing"
    assert run.detail.disclosure.summary == "Quarterly results exceeded expectations."
    assert run.detail.disclosure.source == "sec-edgar"
    assert run.detail.disclosure.reference == "sec://filing/fixture-filing"
    assert run.detail.disclosure.score == 0.78
    assert run.detail.news.title == "Deterministic fixture news"
    assert run.detail.news.summary == "AI accelerator orders expanded."
    assert run.detail.news.source == "reuters.com"
    assert run.detail.news.reference == "https://example.invalid/fixture-news"
    assert run.detail.news.score == 0.74
    assert run.detail.strategy.proposal == "buy"
    assert run.detail.strategy.rationale == "기술·공시·뉴스 합의"
    assert run.detail.strategy.gate == "passed"
    assert run.detail.strategy.blockers == ()
    assert run.detail.strategy.conviction == 0.775
    assert run.detail.critic.verdict == "pass"
    assert run.detail.critic.rationale == "강한 반증과 하드 블로커 없음"
    assert run.detail.critic.layer == "gate"


@pytest.mark.anyio
async def test_critic_hard_block_retains_typed_rejection_detail() -> None:
    # Given
    context = PipelineContext(
        request=PipelineRequest(ticker="NVDA", cycle_ts=NOW),
        side="buy",
        conviction=0.8,
        last_price=100.0,
        macro_regime="risk_off",
    )

    # When
    updated = await Critic(DeterministicAnalyzer()).execute(context)

    # Then
    assert updated.critic_approved is False
    assert updated.critic_verdict is not None
    assert updated.critic_verdict.decision == "reject"
    assert updated.critic_verdict.objection == "risk-off regime"
    assert updated.critic_verdict.decided_layer == "hard_rule"
    detail = updated.to_run().detail
    assert detail.critic.verdict == "reject"
    assert detail.critic.rationale == "risk-off regime"
    assert detail.critic.layer == "hard_rule"


def test_legacy_context_keeps_empty_terminal_detail_placeholders() -> None:
    # Given
    context = PipelineContext(request=PipelineRequest(ticker="NVDA", cycle_ts=NOW))

    # When
    run = context.to_run()

    # Then
    assert run.detail.disclosure.title == ""
    assert run.detail.news.title == ""
    assert run.detail.strategy.proposal == ""
    assert run.detail.critic.verdict == ""


def test_terminal_detail_bounds_untrusted_strategy_rationale() -> None:
    # Given
    source = StrategyInput.fixture()
    strategy = StrategyOutput.from_model(source, conviction=0.8, summary="x" * 1_001)
    context = PipelineContext(
        request=PipelineRequest(ticker="NVDA", cycle_ts=NOW),
        strategy_output=strategy,
    )

    # When
    detail = context.to_run().detail

    # Then
    assert detail.strategy.rationale == "x" * 1_000


@pytest.mark.anyio
async def test_failed_terminal_run_retains_collected_detail() -> None:
    # Given
    request = PipelineRequest(ticker="NVDA", cycle_ts=NOW)
    store = InMemoryRunStore()

    # When
    with pytest.raises(RuntimeError, match="fixture failure"):
        _ = await PipelineOrchestrator(
            (_CollectedDetailRole(), _FailingAfterDetailRole()), store
        ).run(request)

    # Then
    failed = (await store.list_recent())[0]
    assert failed.detail.disclosure.title == "Collected filing"
    assert failed.detail.disclosure.score == 0.78
