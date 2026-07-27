"""Scripted per-ticker analyzer for the demo runtime."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, assert_never

from quantinue.core.ontology import ModelProvider
from quantinue.llm.prompts import load_system_prompt
from quantinue.llm.provider import (
    AnalysisResult,
    AnalysisTask,
    ModelOutput,
    StrategyModelOutput,
    _metadata,
    _narrative,
)
from quantinue.llm.usage_limits import MaximumTokenUsage

if TYPE_CHECKING:
    from collections.abc import Mapping

Stance = Literal["bullish", "bearish"]

_MODEL_NAME = "demo-scenario-mock-v1"


class ScenarioAnalyzer:
    """`LlmAnalyzer` that answers from a fixed per-ticker script.

    운영 mock(DeterministicAnalyzer)은 태스크별 고정 응답이라 "악재 → 매도
    반전"(S4)을 표현할 수 없다. 이 분석기는 각본에 등록된 티커의 성향대로만
    답하고, 미등록·모호한 프롬프트는 hold로 닫아 예상 밖 주문을 금지한다
    (demo-video-plan.md §4-2). 실제 원격 호출과 비용은 0이다.
    """

    def __init__(
        self, *, stances: Mapping[str, Stance], model_name: str = _MODEL_NAME
    ) -> None:
        """Bind the scripted stances; tickers are matched as whole words."""
        self._stances: dict[str, Stance] = {
            ticker.upper(): stance for ticker, stance in stances.items()
        }
        self._model_name = model_name

    def maximum_usage(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> MaximumTokenUsage:
        """Report that the scripted provider cannot incur token charges."""
        _ = (task, prompt, profile)
        return MaximumTokenUsage(model=self._model_name, input_tokens=0, output_tokens=0)

    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        """Map the prompt's scenario ticker to its scripted judgement."""
        system_prompt = load_system_prompt(task.value, profile=profile)
        stance = self._stance_for(prompt)
        output = self._output_for(task, stance)
        return AnalysisResult(
            score=output.score,
            label=output.label,
            reason=output.reason,
            bull_case=_narrative(output.bull_case)
            if isinstance(output, StrategyModelOutput)
            else None,
            key_risk=_narrative(output.key_risk)
            if isinstance(output, StrategyModelOutput)
            else None,
            metadata=_metadata(self._model_name, ModelProvider.MOCK, system_prompt, prompt),
        )

    def _stance_for(self, prompt: str) -> Stance | None:
        """Return the stance only when exactly one scenario ticker matches.

        0개(미등록)와 2개 이상(모호)을 똑같이 None으로 닫는 것이 의도다 —
        어느 각본인지 확정할 수 없을 때 잘못된 매수·매도가 나가는 것보다
        hold(주문 0건)가 데모의 올바른 실패 모드다.
        """
        matched = [
            ticker
            for ticker in self._stances
            if re.search(rf"\b{re.escape(ticker)}\b", prompt.upper())
        ]
        if len(matched) != 1:
            return None
        return self._stances[matched[0]]

    def _output_for(self, task: AnalysisTask, stance: Stance | None) -> ModelOutput:
        """Return the scripted structured output for one task."""
        match task:
            case AnalysisTask.STRATEGY:
                return _strategy_output(stance)
            case AnalysisTask.NEWS | AnalysisTask.DISCLOSURE:
                return _sentiment_output(stance)
            case AnalysisTask.CRITIC:
                return ModelOutput(
                    score=0.82,
                    label="approved",
                    reason="반대 근거를 찾지 못했다 — 집행을 막을 이유 없음",
                )
            case AnalysisTask.REVIEW:
                return ModelOutput(
                    score=0.70, label="consistent", reason="결정 근거와 결과가 일치한다"
                )
            case unreachable:
                assert_never(unreachable)


def _strategy_output(stance: Stance | None) -> StrategyModelOutput:
    """Map a stance to the scripted strategist judgement.

    score가 곧 방향이다 — 전략 경로는 label이 아니라 model_score로
    conviction(매수)과 bearishness(1-score, 매도)를 계산한다(role_07
    contracts). 시드 픽 점수 0.50과 운영 문턱(공격 매수 0.65·매도 0.60,
    안전 매수 0.75·매도 0.50) 기준으로:
      bullish 0.85 → conviction 0.675 = 공격형 매수
      bearish 0.10 → bearishness 0.90 = 양 성향 매도
      미등록 0.60 → conviction 0.55·bearishness 0.40 = hold
    """
    match stance:
        case "bullish":
            return StrategyModelOutput(
                score=0.85,
                label="buy",
                reason="장기 공급 계약으로 실적 가시성이 높아졌다",
                bull_case="계약 물량 확대와 거래량 동반 돌파",
                key_risk="계약 이행이 지연되면 모멘텀이 소멸한다",
            )
        case "bearish":
            return StrategyModelOutput(
                score=0.10,
                label="sell",
                reason="가이던스 철회로 보유 논거가 무너졌다",
                bull_case="",
                key_risk="생산 차질이 길어지면 하방 변동성이 커진다",
            )
        case None:
            return StrategyModelOutput(
                score=0.60,
                label="hold",
                reason="새 근거가 없어 판단을 보류한다",
                bull_case="",
                key_risk="",
            )
        case unreachable:
            assert_never(unreachable)


def _sentiment_output(stance: Stance | None) -> ModelOutput:
    """Map a stance to the scripted news/disclosure grade."""
    match stance:
        case "bullish":
            return ModelOutput(
                score=0.80, label="positive", reason="원문이 실적 개선을 직접 언급한다"
            )
        case "bearish":
            return ModelOutput(
                score=0.20, label="negative", reason="원문이 가이던스 철회를 직접 언급한다"
            )
        case None:
            return ModelOutput(
                score=0.50, label="neutral", reason="판단을 바꿀 만한 내용이 없다"
            )
        case unreachable:
            assert_never(unreachable)
