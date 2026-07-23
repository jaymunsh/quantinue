"""LLM spend ledger and the budget guard that precedes every billable call."""

from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256

import anyio
import pytest
from anyio.lowlevel import checkpoint
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from typing_extensions import override

from quantinue.core.config import LlmMode, Settings
from quantinue.core.ontology import ModelProvider
from quantinue.llm.budget import (
    BudgetedAnalyzer,
    LlmBudgetExceededError,
    LlmUsageRecord,
    ModelPrice,
    require_pricing_for,
)
from quantinue.llm.provider import (
    AnalysisMetadata,
    AnalysisResult,
    AnalysisTask,
    TokenUsage,
)
from quantinue.orchestration.job_factory import build_budgeted_analyzer
from quantinue.orchestration.policy import Mvp2Config

_HASH = sha256(b"prompt").hexdigest()


def _result(model: str, usage: TokenUsage | None) -> AnalysisResult:
    return AnalysisResult(
        score=0.5,
        label="buy",
        reason="근거",
        usage=usage,
        metadata=AnalysisMetadata(
            model=model,
            provider=ModelProvider.OPENAI,
            prompt_version="v1",
            policy_version="p1",
            input_hash=_HASH,
        ),
    )


class RecordingLedger:
    """In-memory stand-in for the tb_llm_usage ledger."""

    def __init__(self, opening_spend: Decimal | float = 0.0) -> None:
        """Start with an already-spent amount for the day under test."""
        self.records: list[LlmUsageRecord] = []
        self._opening = Decimal(str(opening_spend))

    async def llm_spend_on(self, day: date) -> Decimal:
        """Return the day's total, ledger rows included."""
        _ = day
        return self._opening + sum(
            (record.est_cost_usd for record in self.records), Decimal(0)
        )

    async def record_llm_usage(self, record: LlmUsageRecord) -> None:
        """Append one call to the ledger."""
        self.records.append(record)


class StubAnalyzer:
    """Inner analyzer standing in for a real provider call."""

    def __init__(self, usage: TokenUsage | None, model: str = "gpt-x") -> None:
        """Count calls so the guard can be proven to short-circuit."""
        self.calls: int = 0
        self._usage = usage
        self._model = model

    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        """Return a fixed result and remember that it was reached."""
        _ = (task, prompt, profile)
        self.calls += 1
        return _result(self._model, self._usage)


class _BlockingAnalyzer(StubAnalyzer):
    def __init__(self, prompts: tuple[str, ...]) -> None:
        super().__init__(TokenUsage(input_tokens=1_000, output_tokens=500))
        self.entered = {prompt: anyio.Event() for prompt in prompts}
        self.released = {prompt: anyio.Event() for prompt in prompts}

    @override
    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        _ = (task, profile)
        self.calls += 1
        self.entered[prompt].set()
        await self.released[prompt].wait()
        return _result(self._model, self._usage)


def _analyzer(
    inner: StubAnalyzer,
    ledger: RecordingLedger,
    limit: float = 3.0,
    reserve: float = 0.0,
) -> BudgetedAnalyzer:
    return BudgetedAnalyzer(
        inner,
        ledger=ledger,
        daily_limit_usd=limit,
        sell_budget_reserve_ratio=reserve,
        pricing={"gpt-x": ModelPrice(input_usd_per_1m=1.0, output_usd_per_1m=4.0)},
        now=lambda: datetime(2026, 7, 21, 4, 0, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_billable_call_lands_in_the_spend_ledger() -> None:
    ledger = RecordingLedger()
    inner = StubAnalyzer(TokenUsage(input_tokens=1_000, output_tokens=500))

    result = await _analyzer(inner, ledger).analyze(AnalysisTask.STRATEGY, "prompt")

    assert result.score == 0.5
    assert len(ledger.records) == 1
    record = ledger.records[0]
    assert record.task == "strategy"
    assert record.model == "gpt-x"
    assert record.prompt_tokens == 1_000
    assert record.completion_tokens == 500
    # 1,000/1M x $1 + 500/1M x $4 = 0.001 + 0.002
    assert record.est_cost_usd == Decimal("0.003")


@pytest.mark.anyio
async def test_exhausted_budget_stops_the_call_before_the_model_is_reached() -> None:
    """초과했으면 '판단 없이 사는' 게 아니라 '안 사는' 쪽이어야 한다."""
    ledger = RecordingLedger()
    inner = StubAnalyzer(TokenUsage(input_tokens=1_000, output_tokens=500))

    with pytest.raises(LlmBudgetExceededError):
        await _analyzer(inner, ledger, limit=0).analyze(AnalysisTask.STRATEGY, "p")

    assert inner.calls == 0
    assert ledger.records == []


@pytest.mark.anyio
async def test_sell_reserve_blocks_general_calls_but_keeps_sell_calls_open() -> None:
    # Given
    ledger = RecordingLedger(opening_spend=Decimal("2.41"))
    inner = StubAnalyzer(TokenUsage(input_tokens=1_000, output_tokens=500))
    analyzer = _analyzer(inner, ledger, limit=3.0, reserve=0.20)

    # When / Then
    with pytest.raises(LlmBudgetExceededError):
        await analyzer.analyze(AnalysisTask.STRATEGY, "buy")
    result = await analyzer.analyze_reserved(AnalysisTask.STRATEGY, "sell")

    assert result.score == 0.5
    assert inner.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("run", range(12))
async def test_concurrent_calls_cannot_spend_the_same_remaining_budget(run: int) -> None:
    # Given
    ledger = RecordingLedger(opening_spend=Decimal("2.997"))
    losers = tuple(f"loser-{run}-{contender}" for contender in range(15))
    inner = _BlockingAnalyzer(("winner", *losers))
    for contender in range(15):
        loser = f"loser-{run}-{contender}"
        inner.released[loser].set()
    analyzer = _analyzer(inner, ledger)
    outcomes: list[str] = []

    async def call(prompt: str) -> None:
        try:
            _ = await analyzer.analyze(AnalysisTask.STRATEGY, prompt)
            outcomes.append("succeeded")
        except LlmBudgetExceededError:
            outcomes.append("exhausted")

    # When
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(call, "winner")
        await inner.entered["winner"].wait()
        for contender in range(15):
            _ = task_group.start_soon(call, f"loser-{run}-{contender}")
        await checkpoint()
        inner.released["winner"].set()

    # Then
    committed = await ledger.llm_spend_on(date(2026, 7, 21))
    assert sorted(outcomes) == ["exhausted"] * 15 + ["succeeded"]
    assert (inner.calls, committed, analyzer.reserved_usd) == (1, 3, 0)


@pytest.mark.anyio
async def test_cancellation_releases_only_the_callers_reservation() -> None:
    # Given
    ledger = RecordingLedger()
    prompts = ("general-1", "sell", "general-2", "general-3")
    inner = _BlockingAnalyzer(prompts)
    analyzer = _analyzer(inner, ledger, reserve=0.20)
    completed = {prompt: anyio.Event() for prompt in prompts}
    scopes = {prompt: anyio.CancelScope() for prompt in ("general-1", "general-2")}

    async def call(prompt: str, *, reserved: bool = False) -> None:
        try:
            with scopes.get(prompt, anyio.CancelScope()):
                if reserved:
                    _ = await analyzer.analyze_reserved(AnalysisTask.STRATEGY, prompt)
                else:
                    _ = await analyzer.analyze(AnalysisTask.STRATEGY, prompt)
        finally:
            completed[prompt].set()

    async def call_sell() -> None:
        await call("sell", reserved=True)

    # When / Then
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(call, "general-1")
        await inner.entered["general-1"].wait()
        _ = task_group.start_soon(call_sell)
        await inner.entered["sell"].wait()
        assert analyzer.reserved_usd == Decimal(3)

        scopes["general-1"].cancel()
        await completed["general-1"].wait()
        assert analyzer.reserved_usd == Decimal("0.6")

        _ = task_group.start_soon(call, "general-2")
        await inner.entered["general-2"].wait()
        assert analyzer.reserved_usd == Decimal("2.4")
        scopes["general-2"].cancel()
        await completed["general-2"].wait()
        assert analyzer.reserved_usd == Decimal("0.6")

        _ = task_group.start_soon(call, "general-3")
        await inner.entered["general-3"].wait()
        inner.released["general-3"].set()
        await completed["general-3"].wait()
        inner.released["sell"].set()

    assert (analyzer.reserved_usd, inner.calls) == (Decimal(0), 4)
    assert await ledger.llm_spend_on(date(2026, 7, 21)) == Decimal("0.006")


@pytest.mark.anyio
async def test_a_call_that_reports_no_usage_leaves_the_ledger_untouched() -> None:
    """mock은 토큰을 보고하지 않는다. 0원짜리 행으로 원장을 채우지 않는다."""
    ledger = RecordingLedger()
    inner = StubAnalyzer(None)

    result = await _analyzer(inner, ledger).analyze(AnalysisTask.CRITIC, "p")

    assert result.score == 0.5
    assert ledger.records == []


def test_a_billable_model_without_a_declared_rate_refuses_to_start() -> None:
    """요율이 없으면 비용이 늘 0으로 적히고, 그건 예산이 없는 것과 같다."""
    with pytest.raises(ValueError, match="gpt-x"):
        require_pricing_for("gpt-x", {})


def test_a_declared_rate_satisfies_the_startup_check() -> None:
    require_pricing_for("gpt-x", {"gpt-x": ModelPrice(input_usd_per_1m=1.0)})


def test_pricing_is_owned_by_config() -> None:
    config = Mvp2Config.model_validate(
        {
            "budget": {
                "daily_llm_usd": 2.5,
                "model_pricing": {
                    "gpt-4o-mini": {
                        "input_usd_per_1m": 0.15,
                        "output_usd_per_1m": 0.60,
                    }
                },
            }
        }
    )

    assert config.budget.daily_llm_usd == 2.5
    assert config.budget.model_pricing["gpt-4o-mini"].output_usd_per_1m == 0.60


class IsolatedSettings(Settings):
    """개발자의 .env를 읽지 않는 설정 — 실제로 두 번 밟은 함정이다."""

    model_config = SettingsConfigDict(env_file=None, env_prefix="QUANTINUE_", extra="ignore")


def test_a_billable_mode_refuses_to_build_without_declared_pricing() -> None:
    settings = IsolatedSettings(
        llm_mode=LlmMode.OPENAI,
        openai_api_key=SecretStr("k"),
        openai_model="gpt-unpriced",
    )

    with pytest.raises(ValueError, match="gpt-unpriced"):
        build_budgeted_analyzer(settings, Mvp2Config(), ledger=RecordingLedger())


def test_a_free_mode_is_still_metered_and_needs_no_pricing() -> None:
    """로컬도 감싼다 — 콜 규모가 원장에 남아야 전환 전에 비용을 예측할 수 있다."""
    settings = IsolatedSettings(llm_mode=LlmMode.LOCAL, local_llm_api_key=SecretStr("k"))

    analyzer = build_budgeted_analyzer(settings, Mvp2Config(), ledger=RecordingLedger())

    assert isinstance(analyzer, BudgetedAnalyzer)


def test_without_a_ledger_the_analyzer_is_left_unwrapped() -> None:
    """메모리 스토어에는 원장이 없다. 없는 곳에 가드를 세우는 척하지 않는다."""
    settings = IsolatedSettings(llm_mode=LlmMode.MOCK)

    analyzer = build_budgeted_analyzer(settings, Mvp2Config(), ledger=None)

    assert not isinstance(analyzer, BudgetedAnalyzer)
