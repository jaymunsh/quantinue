"""`profiles.*.risk_off_action` — 선언은 있고 소비자는 없던 설정.

config는 공격형에 ``penalty``, 안전형에 ``no_new_buys``를 준다. 그런데
role_08이 risk_off를 **무조건** reject해서 공격형의 penalty가 무시됐다 — 두
성향이 매크로 악화에 똑같이 반응했다. 감점은 이미 확신도 쪽(``macro_penalty``)이
하고 있으므로, 공격형은 그 감점을 받고 판단을 계속하는 것이 선언된 의미다.
"""

from __future__ import annotations

import pytest

from quantinue.roles.role_08_critic.contracts import CriticInput, CriticVerdict


def _input(**changes: object) -> CriticInput:
    return CriticInput.fixture(**changes)  # type: ignore[arg-type]


def test_the_cautious_profile_stops_buying_when_the_regime_turns() -> None:
    """no_new_buys는 문자 그대로다 — 매크로가 나빠지면 새로 사지 않는다."""
    # When
    verdict = CriticVerdict.apply_hard_gates(
        _input(macro_regime="risk_off"), risk_off_action="no_new_buys"
    )

    # Then
    assert verdict is not None
    assert verdict.decision == "reject"
    assert verdict.category == "macro_riskoff"


def test_the_bold_profile_takes_the_penalty_instead_of_the_block() -> None:
    """penalty는 감점이지 차단이 아니다. 감점은 확신도 단계에서 이미 적용됐고,
    여기서 또 막으면 같은 악재로 두 번 벌하는 셈이다."""
    # When
    verdict = CriticVerdict.apply_hard_gates(
        _input(macro_regime="risk_off"), risk_off_action="penalty"
    )

    # Then: 매크로를 이유로 한 종결 판정이 없다
    assert verdict is None or verdict.category != "macro_riskoff"


def test_the_default_stays_the_safe_one() -> None:
    """부르는 쪽이 말하지 않으면 막는다 — 성향을 모르는 경로(구 러너)의 기존
    거동을 그대로 유지해야 이 변경이 조용한 완화가 되지 않는다."""
    # When
    verdict = CriticVerdict.apply_hard_gates(_input(macro_regime="risk_off"))

    # Then
    assert verdict is not None
    assert verdict.category == "macro_riskoff"


@pytest.mark.parametrize("action", ["penalty", "no_new_buys"])
def test_selling_is_never_blocked_by_the_regime(action: str) -> None:
    """risk_off는 파는 것을 막을 이유가 아니라 파는 이유다 — 두 성향 모두."""
    # When
    verdict = CriticVerdict.apply_hard_gates(
        _input(macro_regime="risk_off", side="sell"), risk_off_action=action
    )

    # Then
    assert verdict is None
