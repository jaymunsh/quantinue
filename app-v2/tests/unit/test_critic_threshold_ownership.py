"""One owner for the critic approval threshold.

Two values competed: `mvp2.gates.critic_approval` (0.70, the documented M2
design) and the legacy `mvp.thresholds.critic_approval_score` (0.60). The
factory wired the legacy one, so the system approved buys ten points looser
than every document claimed. `gates` is the owner; the legacy key is gone.
"""

import pytest

from quantinue.llm.provider import AnalysisResult, AnalysisTask, DeterministicAnalyzer
from quantinue.orchestration.policy import GatesConfig
from quantinue.roles.role_08_critic.service import Critic


class _FixedScoreAnalyzer:
    def __init__(self, score: float) -> None:
        self._score = score

    async def analyze(self, task: AnalysisTask, prompt: str) -> AnalysisResult:
        result = await DeterministicAnalyzer().analyze(task, prompt)
        return result.model_copy(update={"score": self._score})


def test_the_threshold_comes_from_gates() -> None:
    critic = Critic(DeterministicAnalyzer(), gates=GatesConfig(critic_approval=0.85))

    assert critic.approval_threshold(conviction=0.5) == 0.85


def test_a_looser_legacy_value_can_no_longer_shadow_gates() -> None:
    # The old wiring let 0.60 win over the documented 0.70.
    critic = Critic(DeterministicAnalyzer(), gates=GatesConfig(critic_approval=0.70))

    assert critic.approval_threshold(conviction=0.5) == 0.70


def test_overconfidence_still_escalates_above_the_gate() -> None:
    critic = Critic(
        DeterministicAnalyzer(),
        gates=GatesConfig(critic_approval=0.70, overconfidence_approval=0.80),
    )

    assert critic.approval_threshold(conviction=0.95) == 0.80


@pytest.mark.anyio
async def test_a_score_between_the_two_old_values_is_now_rejected() -> None:
    # 0.65 passed under the legacy 0.60 and must not under the documented 0.70.
    critic = Critic(_FixedScoreAnalyzer(0.65), gates=GatesConfig(critic_approval=0.70))

    assert critic.approval_threshold(conviction=0.5) > 0.65
