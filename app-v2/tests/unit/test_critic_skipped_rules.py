"""Which critic rules did not apply — the honesty column the UI already reads.

`tb_critic_verdict.skipped_rules`(schema.sql:119)와 계약 필드
(`role_08/contracts.py:104`)와 화면(`core/context_detail.py:627`, "건너뛴 규칙")이
전부 있었는데 **아무도 값을 채우지 않았다** — 유령 감사에서 실재가 확인된 셋 중
하나다. 화면이 늘 "없음"을 보여주는데, 실제로는 매도 판정에서 매수용 게이트
셋이 통째로 건너뛰어진다.
"""

from __future__ import annotations

import pytest

from quantinue.roles.role_08_critic.contracts import CriticInput, CriticVerdict


def _input(side: str) -> CriticInput:
    return CriticInput.fixture(side=side)  # type: ignore[arg-type]


def test_a_buy_is_measured_against_every_rule() -> None:
    """매수는 게이트 전부를 통과해야 한다 — 건너뛴 것이 없어야 정직하다."""
    assert CriticVerdict.skipped_rules_for(_input("buy")) == ()


def test_selling_skips_the_rules_that_ask_whether_it_is_worth_buying() -> None:
    """매도에는 매수용 게이트가 반대로 작동한다(contracts.py의 sell 분기 주석).

    risk_off는 파는 것을 막을 이유가 아니라 파는 이유이고, 근거가 조용하다고
    이미 든 포지션을 못 팔면 조용한 종목만 영원히 남는다. **건너뛴다는 사실
    자체가 기록돼야** 나중에 "왜 이 매도는 검증이 약했나"에 답할 수 있다.
    """
    # When
    skipped = CriticVerdict.skipped_rules_for(_input("sell"))

    # Then
    assert skipped == ("macro_riskoff", "fake_consensus", "evidence_freshness")


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_price_sanity_is_never_skipped(side: str) -> None:
    """값을 매길 수 없으면 팔 수도 없다 — 시세 정합성은 양방향 게이트다."""
    assert "data_quality" not in CriticVerdict.skipped_rules_for(_input(side))


def test_the_skipped_list_survives_onto_the_verdict() -> None:
    """계약 필드가 있는 것과 채워지는 것은 다르다 — 유령이 살던 자리."""
    # Given
    verdict = CriticVerdict(
        run_id="r",
        signal_id=1,
        ticker="AAA",
        decision="reject",
        category="model_review",
        objection="no",
        confidence=0.4,
        decided_layer="llm",
        evidence_ids=("e",),
        skipped_rules=CriticVerdict.skipped_rules_for(_input("sell")),
    )

    # Then
    assert verdict.skipped_rules == (
        "macro_riskoff",
        "fake_consensus",
        "evidence_freshness",
    )
