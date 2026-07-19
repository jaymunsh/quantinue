"""What one ticker looks like on the day it is analysed, and how we ask about it.

구 05·06은 종목당 각각 1콜씩 써서 공시 점수와 뉴스 점수를 따로 냈고, 07은 그
둘을 float 두 개로만 받았다 — 모델은 티커도, 가격도, 무슨 일이 있었는지도 보지
못했다(``f"technical={t}, disclosure={d}, news={n}"``가 프롬프트 전부였다).

여기서는 증거를 **한 덩어리로 종합해** 한 번에 묻는다. 콜 수가 줄어서가 아니라
판단이 맥락을 갖기 위해서다. 특히 **보유 맥락**이 들어가야 07이 "안 사는 것"과
"파는 것"을 구분할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AnalysisSubject:
    """One ticker in today's scope, priced from the last closed session."""

    ticker: str
    rank: int
    score: float
    bucket: str
    close: Decimal
    high: Decimal
    low: Decimal
    close_prev: Decimal | None


@dataclass(frozen=True, slots=True)
class HoldingContext:
    """What we own of this ticker, if anything.

    ``quantity``가 0이면 미보유다. 진입가와 보유일이 함께 오는 이유: "얼마에
    샀는지"만으로는 손실이 굳어가는 중인지 방금 흔들린 것인지 알 수 없다.
    """

    quantity: int = 0
    entry_price: Decimal | None = None
    business_days_held: int = 0


def analysis_prompt(
    subject: AnalysisSubject,
    holding: HoldingContext,
    filings: tuple[str, ...],
    headlines: tuple[str, ...] = (),
) -> str:
    """Compose the one payload the strategist model sees for this ticker.

    모델에 넘기는 문자열은 전부 신뢰할 수 없는 외부 데이터로 취급된다
    (``PydanticAiAnalyzer``가 ``ModelInput.external_data``로 감싼다). 그래서
    여기서는 지시가 아니라 **사실만** 적는다 — 지시는 시스템 프롬프트 소유다.

    보유 중일 때 미실현 손익을 함께 적는 이유: 같은 약세 신호라도 이미 20%
    손실인 포지션과 방금 산 포지션은 다른 결정을 부른다.
    """
    lines = [
        f"ticker={subject.ticker}",
        f"screening_rank={subject.rank} screening_score={subject.score:.4f}"
        f" bucket={subject.bucket}",
        f"close={subject.close} day_high={subject.high} day_low={subject.low}",
    ]
    if subject.close_prev is not None:
        lines.append(f"previous_close={subject.close_prev}")
    if holding.quantity > 0:
        held = [f"held_quantity={holding.quantity}"]
        if holding.entry_price is not None:
            held.append(f"entry_price={holding.entry_price}")
            if holding.entry_price > 0:
                change = (subject.close - holding.entry_price) / holding.entry_price
                held.append(f"unrealized_pct={change * 100:.2f}")
        held.append(f"business_days_held={holding.business_days_held}")
        lines.append(" ".join(held))
    else:
        lines.append("held_quantity=0")
    # 없는 것도 적는다. 증거가 비었다는 사실 자체가 판단 근거이고, 항목이
    # 통째로 빠지면 모델은 "안 알려줬다"와 "없었다"를 구분할 수 없다.
    lines.append(f"filings={','.join(filings) if filings else 'none'}")
    lines.append(f"headlines={' | '.join(headlines) if headlines else 'none'}")
    return "\n".join(lines)
