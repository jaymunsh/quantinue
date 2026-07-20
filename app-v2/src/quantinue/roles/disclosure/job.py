"""The insider scoring job: today's Form 4 filings in, one vote per ticker out.

**왜 별도 잡인가.** 채점이 묻는 것은 "무엇이 사실인가"이지 "내 성향이면 어떻게
보는가"가 아니다 — 답이 성향과 무관하므로 성향 축을 갖지 않는다. 분석 잡 안에서
채점하면 성향 수만큼 같은 질문을 반복하게 된다.

**왜 뉴스도 폼 종류도 아닌 Form 4인가 — 실측이 두 번 기각했다.**
와이어 뉴스(allow 0.95)는 우리 픽을 한 종목도 안 덮었다(픽 날짜 4개 전부 겹침 0 —
마이크로캡·OTC 보도자료가 최신 피드를 지배하고 우리 유니버스는 시총 상위 2000이다).
픽을 덮는 뉴스는 전부 benzinga(gray 0.50)라 문턱에서 표를 잃는다. 그래서 공시로
갔는데, 폼 **종류만** 주고 채점시키자 실 LLM이 6건 전부 0.500을 냈다 — 모델이
"본문 없이는 판단할 수 없다"고 정직하게 거부했고 그 말이 옳았다. 상수 투표는
표가 없는 것보다 나쁘다(공시를 낸 종목만 확신도가 일률 감점되고 그 감점에
정보가 없다).

Form 4가 다른 이유는 하나다: **증거가 필드로 온다.** 거래코드·수량·가격·
10b5-1 여부·직위가 전부 구조화돼 있어서 지어낼 여지가 없고, 문서가 36KB라
받아올 수도 있다(10-Q는 13.7MB였다).

**대부분의 날은 조용하다.** 실측으로 픽의 12~14%만 Form 4를 내고, 그중 재량
거래는 다시 일부다(23건 전수에서 공개시장 매수 1건 · 재량 매도 1건). 그것이
정상이고 설계다 — 없으면 기권하지, 중립값을 지어내지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING, Protocol

from quantinue.db.domain_records import DisclosureSignalWrite
from quantinue.roles.disclosure.insider import InsiderPolicy, score_insider_activity

if TYPE_CHECKING:
    from datetime import date

    from quantinue.market_data.sec_ownership import InsiderTransaction


class _OwnershipSource(Protocol):
    async def transactions(
        self, source_refs: tuple[str, ...]
    ) -> tuple[InsiderTransaction, ...]:
        """Fetch and read the requested Form 4 submissions."""
        ...


@dataclass(frozen=True, slots=True)
class InsiderScore:
    """What one ticker's insiders did, as a vote."""

    ticker: str
    score: float
    transactions: int


@dataclass(frozen=True, slots=True)
class InsiderScoringRun:
    """What one pass over today's scope produced.

    기권 수를 함께 돌려주는 이유: 잡 원장이 "2건 채점"이라고만 적으면 Form 4를
    낸 종목이 7이었다는 사실이 사라진다. 조용한 절단은 "전부 봤다"로 읽힌다.
    """

    scores: tuple[InsiderScore, ...]
    abstained: int = 0


@dataclass(frozen=True, slots=True)
class InsiderScoringJob:
    """Score the insider activity of every ticker in today's analysis scope."""

    store: object
    source: _OwnershipSource
    policy: InsiderPolicy = field(default_factory=InsiderPolicy)

    async def run(self, *, as_of: date, session: date) -> InsiderScoringRun:
        """Fetch the session's Form 4 filings for our scope and vote on them."""
        domain = getattr(self.store, "domain", self.store)
        subjects = await domain.analysis_subjects(as_of, session)
        if not subjects:
            return InsiderScoringRun(())
        tickers = tuple(subject.ticker for subject in subjects)
        filings = await domain.insider_filings(session, tickers)
        if not filings:
            return InsiderScoringRun(())
        # Form 4를 낸 종목만 받는다 — 나머지까지 요청하면 SEC에 쓸데없는 부하를
        # 주고 우리도 느려진다.
        refs = tuple(ref for entry in filings.values() for ref in entry)
        transactions = await self.source.transactions(refs)
        # 한 번에 받은 거래가 여러 종목의 것이다. 발행사 티커로 갈라야
        # 남의 매수가 내 표가 되지 않는다.
        by_ticker: dict[str, list[InsiderTransaction]] = {}
        for item in transactions:
            by_ticker.setdefault(item.ticker, []).append(item)
        cycle_ts = datetime.combine(as_of, time(), tzinfo=UTC)
        scores: list[InsiderScore] = []
        abstained = 0
        for ticker in filings:
            found = tuple(by_ticker.get(ticker, ()))
            score = score_insider_activity(found, self.policy)
            if score is None:
                # 재량 거래가 없었다 — 보상 기계이거나 계획매매다. 침묵이 답이고,
                # 행을 안 쓰는 것이 곧 기권이다(중립값을 쓰면 표가 되어버린다).
                abstained += 1
                continue
            await domain.save_disclosure_signal(
                DisclosureSignalWrite(
                    ticker=ticker,
                    cycle_ts=cycle_ts,
                    trade_date=as_of,
                    has_signal=True,
                    sentiment_score=score,
                    disclosure_count=len(found),
                    model_provider="sec-form4",
                    model_name=None,
                )
            )
            scores.append(
                InsiderScore(ticker=ticker, score=score, transactions=len(found))
            )
        return InsiderScoringRun(tuple(scores), abstained)
