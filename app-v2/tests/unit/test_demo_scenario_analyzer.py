"""Scenario analyzer: scripted per-ticker LLM stances for the demo runtime."""

import pytest

from quantinue.demo.scenario_analyzer import ScenarioAnalyzer
from quantinue.llm.provider import AnalysisTask

# 호재(GOODCO)는 매수, 악재(BADCO)는 매도 반전 — S3·S4 장면의 각본이다.
_STANCES = {"GOODCO": "bullish", "BADCO": "bearish"}


def _analyzer() -> ScenarioAnalyzer:
    return ScenarioAnalyzer(stances=_STANCES)


class TestStrategyStances:
    @pytest.mark.anyio
    async def test_bullish_ticker_returns_buy_with_narrative(self) -> None:
        result = await _analyzer().analyze(
            AnalysisTask.STRATEGY, "GOODCO breakout with new contract", profile="aggressive"
        )
        assert result.label == "buy"
        assert result.bull_case
        assert result.key_risk

    @pytest.mark.anyio
    async def test_bearish_ticker_returns_sell_reversal(self) -> None:
        result = await _analyzer().analyze(
            AnalysisTask.STRATEGY, "BADCO guidance withdrawn", profile="conservative"
        )
        assert result.label == "sell"

    @pytest.mark.anyio
    async def test_unknown_ticker_closes_to_hold(self) -> None:
        result = await _analyzer().analyze(AnalysisTask.STRATEGY, "TSLA unrelated prompt")
        assert result.label == "hold"

    @pytest.mark.anyio
    async def test_ambiguous_prompt_closes_to_hold(self) -> None:
        # 각본 티커 둘이 한 프롬프트에 섞이면 어느 각본인지 확정할 수 없다.
        # 잘못된 매수·매도보다 hold(주문 0건)가 데모의 실패 모드다.
        result = await _analyzer().analyze(AnalysisTask.STRATEGY, "GOODCO vs BADCO pair")
        assert result.label == "hold"


class TestOtherTasks:
    @pytest.mark.anyio
    async def test_critic_always_approves(self) -> None:
        for prompt in ("GOODCO judgement", "BADCO judgement", "TSLA judgement"):
            result = await _analyzer().analyze(AnalysisTask.CRITIC, prompt)
            assert result.label == "approved"

    @pytest.mark.anyio
    async def test_news_score_follows_stance(self) -> None:
        analyzer = _analyzer()
        good = await analyzer.analyze(AnalysisTask.NEWS, "GOODCO wins contract")
        bad = await analyzer.analyze(AnalysisTask.NEWS, "BADCO recall widens")
        assert good.label == "positive"
        assert bad.label == "negative"


class TestDeterminismAndCost:
    @pytest.mark.anyio
    async def test_same_prompt_returns_identical_result(self) -> None:
        analyzer = _analyzer()
        first = await analyzer.analyze(AnalysisTask.STRATEGY, "GOODCO breakout")
        second = await analyzer.analyze(AnalysisTask.STRATEGY, "GOODCO breakout")
        assert first == second

    def test_maximum_usage_is_free(self) -> None:
        usage = _analyzer().maximum_usage(AnalysisTask.STRATEGY, "GOODCO breakout")
        assert (usage.input_tokens, usage.output_tokens) == (0, 0)

    @pytest.mark.anyio
    async def test_lineage_marks_the_demo_model(self) -> None:
        result = await _analyzer().analyze(AnalysisTask.STRATEGY, "GOODCO breakout")
        assert result.metadata.model == "demo-scenario-mock-v1"
        assert result.usage is None
