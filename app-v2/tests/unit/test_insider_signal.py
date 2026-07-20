"""내부자 신호 정책 — 무엇이 판단이고 무엇이 급여인가.

실측(픽에 걸린 Form 4 23건 전수)이 이 정책의 근거다: 거래 79건 중 보상 기계
(부여 A 26 · 세금원천 F 10 · 옵션행사 M·C 4)가 절반이고, 매도 38건은 큰 묶음이
전부 10b5-1 계획매매였다. 실제 재량 거래는 **공개시장 매수 1건**뿐이었다.
"""

from __future__ import annotations

from decimal import Decimal

from quantinue.market_data.sec_ownership import InsiderTransaction
from quantinue.roles.disclosure.insider import InsiderPolicy, score_insider_activity


def _transaction(
    code: str,
    *,
    acquired: bool,
    planned: bool = False,
    shares: int = 100,
    price: str | None = "50.00",
) -> InsiderTransaction:
    return InsiderTransaction(
        ticker="AAA",
        code=code,
        acquired=acquired,
        shares=Decimal(shares),
        price=None if price is None else Decimal(price),
        is_planned=planned,
        is_officer=True,
        is_director=False,
        is_ten_percent_owner=False,
        officer_title="Chief Executive Officer",
    )


_POLICY = InsiderPolicy()


def test_an_open_market_purchase_is_a_bullish_vote() -> None:
    """자기 돈으로 시장에서 산 것 — 이 표가 이 작업의 존재 이유다."""
    score = score_insider_activity((_transaction("P", acquired=True),), _POLICY)

    assert score is not None
    assert score > 0.5


def test_a_discretionary_sale_is_a_bearish_vote() -> None:
    """계획에 없던 매도는 판단이다."""
    score = score_insider_activity((_transaction("S", acquired=False),), _POLICY)

    assert score is not None
    assert score < 0.5


def test_a_planned_sale_is_not_a_vote_at_all() -> None:
    """10b5-1은 몇 달 전에 짜둔 일정이라 오늘의 판단이 아니다. 실측 매도 38건 중
    큰 묶음이 전부 여기였다 — 이 필터가 없으면 신호가 노이즈에 잠긴다."""
    assert (
        score_insider_activity(
            (_transaction("S", acquired=False, planned=True),), _POLICY
        )
        is None
    )


def test_compensation_mechanics_are_not_votes() -> None:
    """부여·세금원천·옵션행사는 급여의 기계다. 내부자가 고른 것이 아니다."""
    payroll = (
        _transaction("A", acquired=True, price=None),
        _transaction("F", acquired=False),
        _transaction("M", acquired=True),
    )

    assert score_insider_activity(payroll, _POLICY) is None


def test_nothing_informative_abstains_instead_of_scoring_neutral() -> None:
    """상수 중립값은 표가 없는 것보다 나쁘다 — 실측으로 확인된 실패 모드다."""
    assert score_insider_activity((), _POLICY) is None


def test_the_net_direction_decides_when_an_insider_both_buys_and_sells() -> None:
    """같은 날 사고 팔면 방향은 금액이 정한다 — 건수는 규모를 말하지 않는다."""
    mixed = (
        _transaction("P", acquired=True, shares=1_000, price="100.00"),
        _transaction("S", acquired=False, shares=10, price="100.00"),
    )

    score = score_insider_activity(mixed, _POLICY)

    assert score is not None
    assert score > 0.5


def test_a_net_zero_day_abstains_rather_than_inventing_a_direction() -> None:
    """정확히 상쇄되면 우리가 말할 수 있는 것이 없다."""
    offsetting = (
        _transaction("P", acquired=True, shares=100, price="100.00"),
        _transaction("S", acquired=False, shares=100, price="100.00"),
    )

    assert score_insider_activity(offsetting, _POLICY) is None


def test_a_purchase_without_a_price_still_counts_as_a_buy() -> None:
    """가격이 빠진 제출이 방향까지 지우면 안 된다 — 수량으로라도 방향은 안다."""
    score = score_insider_activity(
        (_transaction("P", acquired=True, price=None),), _POLICY
    )

    assert score is not None
    assert score > 0.5
