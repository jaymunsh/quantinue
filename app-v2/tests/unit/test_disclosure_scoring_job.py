"""인사이더 채점 잡 — 내부자가 고른 거래만 07의 표가 된다.

이 파일은 폼 종류 채점을 고정하던 테스트를 대체한다. 그 설계는 실 LLM에서
6건 전부 0.500으로 죽었다(본문 없이는 판단이 불가능하다는 모델의 거부가 옳았다).
Form 4는 증거가 필드로 오므로 채점이 성립하고, 없을 때는 기권한다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quantinue.market_data.sec_ownership import InsiderTransaction
from quantinue.roles.analysis.contracts import AnalysisSubject
from quantinue.roles.disclosure.insider import InsiderPolicy
from quantinue.roles.disclosure.job import InsiderScoringJob

_AS_OF = date(2026, 7, 17)
_SESSION = date(2026, 7, 16)


def _transaction(
    ticker: str, code: str, *, acquired: bool, planned: bool = False
) -> InsiderTransaction:
    return InsiderTransaction(
        ticker=ticker,
        code=code,
        acquired=acquired,
        shares=Decimal(500),
        price=Decimal("100.00"),
        is_planned=planned,
        is_officer=True,
        is_director=False,
        is_ten_percent_owner=False,
        officer_title="Chief Executive Officer",
    )


def _subject(ticker: str, rank: int) -> AnalysisSubject:
    return AnalysisSubject(
        ticker=ticker,
        rank=rank,
        score=0.9,
        bucket="trend_leader",
        close=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close_prev=Decimal(98),
    )


class _Source:
    def __init__(self, transactions: tuple[InsiderTransaction, ...] = ()) -> None:
        self._transactions = transactions
        self.requested: list[tuple[str, ...]] = []

    async def transactions(
        self, source_refs: tuple[str, ...]
    ) -> tuple[InsiderTransaction, ...]:
        self.requested.append(source_refs)
        return self._transactions


class _Domain:
    def __init__(
        self, subjects: tuple[str, ...], filings: dict[str, tuple[str, ...]]
    ) -> None:
        self._subjects = tuple(
            _subject(ticker, index + 1) for index, ticker in enumerate(subjects)
        )
        self._filings = filings
        self.saved: list[object] = []

    async def analysis_subjects(
        self, as_of: date, session: date
    ) -> tuple[AnalysisSubject, ...]:
        return self._subjects

    async def insider_filings(
        self, session: date, tickers: tuple[str, ...]
    ) -> dict[str, tuple[str, ...]]:
        return {t: refs for t, refs in self._filings.items() if t in tickers}

    async def save_disclosure_signal(self, value: object) -> None:
        self.saved.append(value)


def _job(domain: _Domain, source: _Source) -> InsiderScoringJob:
    return InsiderScoringJob(store=domain, source=source, policy=InsiderPolicy())


@pytest.mark.anyio
async def test_an_open_market_purchase_becomes_a_bullish_vote() -> None:
    """자기 돈으로 시장에서 산 것 — 이 표가 이 잡의 존재 이유다."""
    domain = _Domain(("AAA",), {"AAA": ("edgar/a.txt",)})
    source = _Source((_transaction("AAA", "P", acquired=True),))

    run = await _job(domain, source).run(as_of=_AS_OF, session=_SESSION)

    assert [score.ticker for score in run.scores] == ["AAA"]
    assert run.scores[0].score > 0.5
    (saved,) = domain.saved
    assert saved.cycle_ts == datetime.combine(_AS_OF, datetime.min.time(), tzinfo=UTC)
    assert saved.sentiment_score > 0.5


@pytest.mark.anyio
async def test_a_planned_sale_writes_no_row_at_all() -> None:
    """기권은 중립값이 아니라 침묵이다 — 행이 없어야 07이 표로 세지 않는다."""
    domain = _Domain(("AAA",), {"AAA": ("edgar/a.txt",)})
    source = _Source((_transaction("AAA", "S", acquired=False, planned=True),))

    run = await _job(domain, source).run(as_of=_AS_OF, session=_SESSION)

    assert run.scores == ()
    assert run.abstained == 1
    assert domain.saved == []


@pytest.mark.anyio
async def test_only_the_tickers_that_filed_are_fetched() -> None:
    """Form 4가 없는 종목까지 문서를 받으면 SEC에 쓸데없는 요청을 보낸다."""
    domain = _Domain(("AAA", "BBB"), {"AAA": ("edgar/a.txt",)})
    source = _Source((_transaction("AAA", "P", acquired=True),))

    _ = await _job(domain, source).run(as_of=_AS_OF, session=_SESSION)

    assert source.requested == [("edgar/a.txt",)]


@pytest.mark.anyio
async def test_transactions_are_grouped_by_the_ticker_that_filed_them() -> None:
    """한 번에 받은 거래가 여러 종목의 것이다 — 섞으면 남의 매수가 내 표가 된다."""
    domain = _Domain(("AAA", "BBB"), {"AAA": ("edgar/a.txt",), "BBB": ("edgar/b.txt",)})
    source = _Source(
        (
            _transaction("AAA", "P", acquired=True),
            _transaction("BBB", "S", acquired=False),
        )
    )

    run = await _job(domain, source).run(as_of=_AS_OF, session=_SESSION)

    by_ticker = {score.ticker: score.score for score in run.scores}
    assert by_ticker["AAA"] > 0.5
    assert by_ticker["BBB"] < 0.5


@pytest.mark.anyio
async def test_a_day_with_no_insider_filings_is_a_quiet_success() -> None:
    """대부분의 날이 이렇다 — 조용한 것이 정상이지 실패가 아니다."""
    domain = _Domain(("AAA",), {})

    run = await _job(domain, _Source()).run(as_of=_AS_OF, session=_SESSION)

    assert run.scores == ()
    assert run.abstained == 0
