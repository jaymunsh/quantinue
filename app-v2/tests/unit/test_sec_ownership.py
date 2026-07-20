"""Form 4 파서 — 내부자 거래를 지어내지 않고 읽는다.

폼 종류만으로는 채점이 안 된다는 것을 실 LLM이 증명했다(6건 전부 0.500).
Form 4는 다르다: 거래코드·수량·가격·10b5-1 플래그가 전부 **필드로** 있어서
추론할 것이 없다. 그래서 여기 파서는 판단을 하지 않고 낭독만 한다.
"""

from __future__ import annotations

from decimal import Decimal

from quantinue.market_data.sec_ownership import parse_ownership_form4

# 실 제출(NET 0001473289-26-000018)의 구조를 그대로 줄인 것.
_PURCHASE = """
<SEC-DOCUMENT>
<XML>
<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport>2026-07-15</periodOfReport>
  <issuer>
    <issuerName>Texas Pacific Land Corp</issuerName>
    <issuerTradingSymbol>TPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>HORIZON KINETICS</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>0</isOfficer>
      <isTenPercentOwner>1</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1200</value></transactionShares>
        <transactionPricePerShare><value>975.40</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
</XML>
</SEC-DOCUMENT>
"""


def test_an_open_market_purchase_is_read_field_by_field() -> None:
    """추론이 아니라 낭독이다 — 값 하나하나가 제출 서류에 그대로 있다."""
    (transaction,) = parse_ownership_form4(_PURCHASE)

    assert transaction.ticker == "TPL"
    assert transaction.code == "P"
    assert transaction.acquired is True
    assert transaction.shares == Decimal(1200)
    assert transaction.price == Decimal("975.40")
    assert transaction.is_planned is False
    assert transaction.is_ten_percent_owner is True
    assert transaction.is_officer is False


def test_a_planned_sale_is_marked_as_planned() -> None:
    """10b5-1은 미리 짜둔 매도라 판단이 아니다. 이 플래그가 노이즈 분리의 전부다."""
    document = _PURCHASE.replace(
        "<aff10b5One>0</aff10b5One>", "<aff10b5One>1</aff10b5One>"
    ).replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")

    (transaction,) = parse_ownership_form4(document)

    assert transaction.code == "S"
    assert transaction.is_planned is True


def test_every_transaction_in_one_filing_is_returned() -> None:
    """한 제출에 거래가 여럿이다(실측: CRWD 한 건에 매도 18건). 첫 줄만 읽으면 규모를 잃는다."""
    second = """
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>50</value></transactionShares>
        <transactionPricePerShare><value>975.40</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    """
    document = _PURCHASE.replace("</nonDerivativeTable>", f"{second}</nonDerivativeTable>")

    transactions = parse_ownership_form4(document)

    assert [item.code for item in transactions] == ["P", "F"]
    assert [item.acquired for item in transactions] == [True, False]


def test_a_filing_without_an_ownership_document_yields_nothing() -> None:
    """받은 것이 Form 4가 아니면 조용히 비운다 — 지어내느니 기권한다."""
    assert parse_ownership_form4("<SEC-DOCUMENT>not ownership</SEC-DOCUMENT>") == ()


def test_a_transaction_without_a_price_is_still_read() -> None:
    """부여(A)에는 가격이 없다. 없는 값을 0으로 읽으면 '공짜로 샀다'가 된다."""
    document = _PURCHASE.replace(
        "<transactionPricePerShare><value>975.40</value></transactionPricePerShare>", ""
    )

    (transaction,) = parse_ownership_form4(document)

    assert transaction.price is None
