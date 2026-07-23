from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256

import pytest

from quantinue.core.ontology import ModelProvider
from quantinue.llm.budget import (
    BudgetedAnalyzer,
    LlmBudgetExceededError,
    LlmUsageMissingError,
    LlmUsageRecord,
    ModelPrice,
)
from quantinue.llm.provider import (
    AnalysisMetadata,
    AnalysisResult,
    AnalysisTask,
    LlmAnalyzer,
)
from quantinue.llm.usage_limits import MaximumTokenUsage


class MissingUsageLedger:
    def __init__(self, committed: Decimal) -> None:
        self.committed = committed
        self.records: list[LlmUsageRecord] = []

    async def llm_spend_on(self, day: date) -> Decimal:
        _ = day
        return self.committed + sum(
            (record.est_cost_usd for record in self.records), Decimal(0)
        )

    async def record_llm_usage(self, record: LlmUsageRecord) -> None:
        self.records.append(record)


class MissingUsageAnalyzer:
    def __init__(self, maximum: MaximumTokenUsage) -> None:
        self.maximum = maximum
        self.calls = 0

    def maximum_usage(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> MaximumTokenUsage:
        _ = (task, prompt, profile)
        return self.maximum

    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        _ = (task, profile)
        self.calls += 1
        return AnalysisResult(
            score=0.5,
            label="fixture",
            reason="missing usage",
            metadata=AnalysisMetadata(
                model=self.maximum.model,
                provider=ModelProvider.OPENAI,
                prompt_version="v1",
                policy_version="p1",
                input_hash=sha256(prompt.encode()).hexdigest(),
            ),
        )


def budgeted(
    inner: LlmAnalyzer,
    ledger: MissingUsageLedger,
    pricing: dict[str, ModelPrice],
) -> BudgetedAnalyzer:
    return BudgetedAnalyzer(
        inner,
        ledger=ledger,
        daily_limit_usd=3,
        pricing=pricing,
        now=lambda: datetime(2026, 7, 23, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_missing_billable_usage_commits_maximum_and_blocks_next_call() -> None:
    # Given
    maximum = MaximumTokenUsage(
        model="gpt-x", input_tokens=3_000, output_tokens=0
    )
    inner = MissingUsageAnalyzer(maximum)
    ledger = MissingUsageLedger(Decimal("2.997"))
    analyzer = budgeted(
        inner, ledger, {"gpt-x": ModelPrice(input_usd_per_1m=1)}
    )

    # When / Then
    with pytest.raises(LlmUsageMissingError):
        await analyzer.analyze(AnalysisTask.STRATEGY, "first")
    with pytest.raises(LlmBudgetExceededError):
        await analyzer.analyze(AnalysisTask.STRATEGY, "second")

    assert inner.calls == 1
    assert ledger.records[0].prompt_tokens == 3_000
    assert ledger.records[0].est_cost_usd == Decimal("0.003")


@pytest.mark.anyio
async def test_zero_cost_provider_may_omit_usage_without_accounting() -> None:
    # Given
    maximum = MaximumTokenUsage(model="local-x", input_tokens=0, output_tokens=0)
    inner = MissingUsageAnalyzer(maximum)
    ledger = MissingUsageLedger(Decimal("2.997"))
    analyzer = budgeted(inner, ledger, {})

    # When
    _ = await analyzer.analyze(AnalysisTask.STRATEGY, "local")

    # Then
    assert inner.calls == 1
    assert ledger.records == []
    assert analyzer.reserved_usd == 0


def test_budget_wrapper_delegates_maximum_usage_as_analyzer_protocol() -> None:
    # Given
    maximum = MaximumTokenUsage(
        model="gpt-x", input_tokens=3_000, output_tokens=0
    )
    inner = MissingUsageAnalyzer(maximum)
    analyzer: LlmAnalyzer = budgeted(inner, MissingUsageLedger(Decimal(0)), {})

    # When
    observed = analyzer.maximum_usage(AnalysisTask.STRATEGY, "prompt")

    # Then
    assert observed == maximum
