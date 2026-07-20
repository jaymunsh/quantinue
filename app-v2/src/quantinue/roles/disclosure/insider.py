"""Turn insider transactions into the vote role_07 counts, or into silence.

**왜 LLM이 아닌가.** 입력이 전부 범주형 사실(거래코드·계획 플래그·수량·가격)이라
모델이 더할 판단이 없다. 그리고 바로 앞 시도에서 봤듯이, 판단할 근거가 없는
자리에 모델을 세우면 정직한 모델은 0.5로 도망친다 — 그 상수가 판단을 오염시켰다.
여기서는 정책을 코드로 적고 문턱은 config가 소유한다(``macro_penalty_table``과 같은 층).

**무엇이 신호인가 — 실측이 정했다.** 픽에 걸린 Form 4 23건(거래 79건)에서:
부여 A 26 · 세금원천 F 10 · 옵션행사 M·C 4는 내부자가 **고른 것이 아니라**
보상 계약이 굴러간 것이고, 매도 38건은 큰 묶음이 전부 10b5-1 계획매매였다.
남은 재량 거래는 공개시장 매수 1건. 그래서 그 하나만 표가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from quantinue.market_data.sec_ownership import InsiderTransaction

# 공개시장 재량 거래의 코드. 나머지(A 부여·F 세금원천·M·C 옵션행사·G 증여 등)는
# 급여와 계약의 기계라 "이 사람이 이 회사를 어떻게 보는가"를 말하지 않는다.
_DISCRETIONARY: Final = frozenset({"P", "S"})


@dataclass(frozen=True, slots=True)
class InsiderPolicy:
    """What a discretionary insider trade is worth as evidence.

    방향만 있고 크기가 없는 이유: 금액을 점수에 매핑하려면 "얼마부터 큰 거래인가"를
    정해야 하는데 우리에겐 그것을 재본 데이터가 없다. 추정해 박느니 방향만
    말한다 — 실측 없는 정밀도는 정밀도가 아니다.
    """

    buy_score: float = 0.80
    sell_score: float = 0.30


def score_insider_activity(
    transactions: tuple[InsiderTransaction, ...], policy: InsiderPolicy
) -> float | None:
    """Score one ticker's insider activity, or abstain when nothing was chosen.

    None은 "중립"이 아니라 **기권**이다. 부르는 쪽은 이 값을 투표에 넣지 않는다 —
    상수 중립값을 넣으면 그 종목만 확신도가 평균 쪽으로 끌려가고, 그 감점에는
    정보가 하나도 없다(실측으로 확인된 실패 모드다).
    """
    net = Decimal(0)
    for item in transactions:
        if item.code not in _DISCRETIONARY or item.is_planned:
            continue
        # 가격이 빠진 제출에서도 방향은 안다. 0으로 읽어 금액을 지우면 그 거래가
        # 없던 일이 되므로, 수량만으로라도 세운다.
        value = item.shares * (item.price if item.price is not None else Decimal(1))
        net += value if item.acquired else -value
    if net > 0:
        return policy.buy_score
    if net < 0:
        return policy.sell_score
    # 재량 거래가 없었거나 정확히 상쇄됐다. 둘 다 우리가 할 말이 없는 날이다.
    return None
