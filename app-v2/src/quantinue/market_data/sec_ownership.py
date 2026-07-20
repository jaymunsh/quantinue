"""Read SEC Form 4 ownership documents into insider transactions.

**왜 파싱이지 채점이 아닌가.** 공시를 폼 종류만으로 채점하려던 시도가 실 LLM에서
6건 전부 0.500으로 죽었다 — 모델이 정직하게 "본문 없이는 판단할 수 없다"고
거부했고 그 말이 맞았다. Form 4는 다르다: 거래코드·수량·가격·10b5-1 여부·직위가
**전부 필드로** 온다. 추론할 것이 없으므로 여기서는 읽기만 하고, 무엇이 신호인지는
``roles/disclosure/insider.py``의 정책이 정한다.

전체 제출 문서(.txt)를 그대로 받는다 — Form 4는 실측 36KB로 작다(10-Q는 13.7MB라
같은 방식이 불가능했다). ``<ownershipDocument>``만 잘라 읽는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Final

import httpx as httpx2

from quantinue.market_data.http_client import sec_user_agent

_ARCHIVES: Final = "https://www.sec.gov/Archives/{ref}"

_DOCUMENT: Final = re.compile(r"<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)
_TRANSACTION: Final = re.compile(
    r"<(nonDerivative|derivative)Transaction>.*?</\1Transaction>", re.DOTALL
)


def _tag(source: str, name: str) -> str | None:
    """Return the first value of a tag, ignoring the <value> wrapper SEC nests."""
    match = re.search(rf"<{name}>(.*?)</{name}>", source, re.DOTALL)
    if match is None:
        return None
    inner = match.group(1)
    nested = re.search(r"<value>(.*?)</value>", inner, re.DOTALL)
    return (nested.group(1) if nested else inner).strip()


def _decimal(source: str, name: str) -> Decimal | None:
    raw = _tag(source, name)
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        # 지어내지 않는다 — 못 읽은 수치는 없는 것으로 둔다.
        return None


def _flag(source: str, name: str) -> bool:
    return (_tag(source, name) or "0").strip() in {"1", "true", "TRUE"}


@dataclass(frozen=True, slots=True)
class InsiderTransaction:
    """One reported insider transaction, exactly as the filing states it."""

    ticker: str
    code: str
    acquired: bool
    shares: Decimal
    price: Decimal | None
    # 10b5-1 계획매매 여부. 노이즈 분리의 전부가 이 한 필드다 — 미리 짜둔 매도는
    # 오늘의 판단이 아니라 몇 달 전의 일정이다.
    is_planned: bool
    is_officer: bool
    is_director: bool
    is_ten_percent_owner: bool
    officer_title: str | None


def parse_ownership_form4(document: str) -> tuple[InsiderTransaction, ...]:
    """Parse every transaction in one Form 4 submission."""
    found = _DOCUMENT.search(document)
    if found is None:
        # Form 4가 아니거나 형식이 다르면 비운다. 반쯤 읽은 것을 신호로 쓰면
        # 그게 곧 지어내기다.
        return ()
    body = found.group(0)
    ticker = _tag(body, "issuerTradingSymbol")
    if not ticker:
        return ()
    planned = _flag(body, "aff10b5One")
    officer = _flag(body, "isOfficer")
    director = _flag(body, "isDirector")
    ten_percent = _flag(body, "isTenPercentOwner")
    title = _tag(body, "officerTitle") or None
    transactions: list[InsiderTransaction] = []
    for match in _TRANSACTION.finditer(body):
        block = match.group(0)
        code = _tag(block, "transactionCode")
        shares = _decimal(block, "transactionShares")
        if code is None or shares is None:
            continue
        transactions.append(
            InsiderTransaction(
                ticker=ticker.upper(),
                code=code,
                acquired=(_tag(block, "transactionAcquiredDisposedCode") or "") == "A",
                shares=shares,
                price=_decimal(block, "transactionPricePerShare"),
                is_planned=planned,
                is_officer=officer,
                is_director=director,
                is_ten_percent_owner=ten_percent,
                officer_title=title,
            )
        )
    return tuple(transactions)


@dataclass(frozen=True, slots=True)
class SecOwnershipSource:
    """Fetch Form 4 submissions and read the insider transactions inside them.

    문서를 통째로 받는 것이 낭비가 아닌 이유는 규모다 — 채점 대상은 그날 픽 중
    Form 4를 낸 종목뿐이라 실측 하루 3~7건이고, 한 건이 36KB다. 같은 방식이
    10-Q에는 불가능했다(13.7MB).

    한 문서의 실패가 나머지를 죽이지 않는다. 내부자 거래는 종목마다 독립적인
    사실이라, 하나를 못 읽었다고 다른 종목의 표까지 잃을 이유가 없다.
    """

    transport: httpx2.AsyncBaseTransport | None = field(default=None)
    timeout_seconds: float = 30.0

    async def transactions(
        self, source_refs: tuple[str, ...]
    ) -> tuple[InsiderTransaction, ...]:
        """Return every insider transaction across the requested filings."""
        if not source_refs:
            return ()
        collected: list[InsiderTransaction] = []
        async with httpx2.AsyncClient(
            transport=self.transport,
            timeout=self.timeout_seconds,
            headers={"User-Agent": sec_user_agent()},
        ) as client:
            for ref in source_refs:
                try:
                    response = await client.get(_ARCHIVES.format(ref=ref.lstrip("/")))
                    _ = response.raise_for_status()
                except httpx2.HTTPError:
                    # 못 읽은 제출은 없는 것으로 둔다. 지어내지 않고, 다른
                    # 종목의 사실을 인질로 잡지도 않는다.
                    continue
                collected.extend(parse_ownership_form4(response.text))
        return tuple(collected)
