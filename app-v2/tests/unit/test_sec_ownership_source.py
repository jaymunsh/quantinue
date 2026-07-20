"""Form 4 수신 — 대상이 하루 몇 건이라 문서를 통째로 받아도 싸다."""

from __future__ import annotations

import httpx as httpx2
import pytest

from quantinue.market_data.sec_ownership import SecOwnershipSource

_DOC = """
<ownershipDocument>
  <issuer><issuerTradingSymbol>TPL</issuerTradingSymbol></issuer>
  <reportingOwnerRelationship><isTenPercentOwner>1</isTenPercentOwner></reportingOwnerRelationship>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTransaction>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>1200</value></transactionShares>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>
"""


class _Recorder:
    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx2.Request] = []
        self._status = status

    def transport(self) -> httpx2.MockTransport:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return httpx2.Response(self._status, text=_DOC)

        return httpx2.MockTransport(handle)


@pytest.mark.anyio
async def test_a_filing_reference_becomes_its_transactions() -> None:
    """원장에 있는 것은 접수 경로뿐이라, 거래를 알려면 문서를 받아야 한다."""
    recorder = _Recorder()
    source = SecOwnershipSource(transport=recorder.transport())

    transactions = await source.transactions(("edgar/data/1/0001-26-1.txt",))

    assert [item.code for item in transactions] == ["P"]
    assert str(recorder.requests[0].url).endswith("Archives/edgar/data/1/0001-26-1.txt")


@pytest.mark.anyio
async def test_the_sec_contact_header_is_sent() -> None:
    """SEC 공정접근 정책이 연락처 담긴 User-Agent를 요구한다 — 없으면 차단된다."""
    recorder = _Recorder()
    source = SecOwnershipSource(transport=recorder.transport())

    _ = await source.transactions(("edgar/data/1/0001-26-1.txt",))

    assert recorder.requests[0].headers["User-Agent"]


@pytest.mark.anyio
async def test_one_unreadable_filing_does_not_lose_the_others() -> None:
    """한 문서가 404여도 나머지 내부자 거래는 여전히 사실이다."""
    ok = httpx2.Response(200, text=_DOC)

    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("bad.txt"):
            return httpx2.Response(404, text="not found")
        return ok

    source = SecOwnershipSource(transport=httpx2.MockTransport(handle))

    transactions = await source.transactions(
        ("edgar/data/1/bad.txt", "edgar/data/1/0001-26-1.txt")
    )

    assert [item.code for item in transactions] == ["P"]
