"""Background collection volume for the demo runtime.

각본 기사 2건만 흘리면 관제실이 "뉴스 2건 · 공시 0건"으로 보인다. 실제
운영은 하루에 수백 건을 모아 **결정론 필터로 걸러낸 뒤** 관련 종목만
판단하는데, 그 규모가 화면에 안 나오면 시스템이 아무 일도 안 하는 것처럼
읽힌다. 그래서 배경 수집물을 함께 흘린다.

배경 종목은 전부 오늘의 분석 범위 **밖**이라 라우팅이 `unrelated_ticker`로
막는다 — 즉 이 데이터는 "수집량"은 늘리지만 LLM 호출은 한 건도 만들지
않는다. 화면에는 "많이 모았고, 그중 관련된 것만 판단했다"가 그대로 남는다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from quantinue.db.domain_records import RawDisclosureWrite, RawNewsWrite

if TYPE_CHECKING:
    from datetime import date, datetime

_SOURCE = "demo:market-wire"

# 배경 종목도 실존 티커와 겹치지 않는 가공 심볼이다(각본 종목과 같은 원칙).
_BACKGROUND: tuple[tuple[str, str], ...] = (
    ("ALTQ", "Altiqua Systems"),
    ("BRYN", "Bryndel Foods"),
    ("CNTV", "Centriva Health"),
    ("DRVO", "Darvo Logistics"),
    ("EMBR", "Embershaw Energy"),
    ("FLXO", "Flexoria Semiconductor"),
    ("GRVN", "Gravenor Mining"),
    ("HYPR", "Hyperia Cloud"),
    ("IONV", "Ionvale Chemical"),
    ("JUNP", "Junipex Retail"),
    ("KLTR", "Kaltera Motors"),
    ("LUMN", "Luminaq Optics"),
    ("MRTH", "Marthex Insurance"),
    ("NEXO", "Nexolon Telecom"),
    ("ORVY", "Orvayne Aerospace"),
    ("PLTA", "Peltara Utilities"),
    ("QRVN", "Quirvon Media"),
    ("RDSK", "Redisko Apparel"),
    ("SVLT", "Sevolt Batteries"),
    ("TRVA", "Torvaya Shipping"),
)

_HEADLINES: tuple[str, ...] = (
    "{company} opens new distribution center",
    "{company} names chief operating officer",
    "{company} expands partnership in Southeast Asia",
    "{company} completes routine facility maintenance",
    "Analysts note steady volume at {company}",
    "{company} publishes sustainability report",
    "{company} schedules investor day",
)

_FORMS: tuple[tuple[str, bool], ...] = (
    ("8-K", False),
    ("10-Q", False),
    ("4", False),
    ("S-3", False),
)


def background_articles(*, published_from: datetime, count: int = 42) -> tuple[RawNewsWrite, ...]:
    """Build routine market noise the routing layer is expected to discard.

    ``article_id``는 각본 기사(1·2)와 겹치지 않게 1000번대부터 쓴다 — 같은
    키가 겹치면 재수집 dedup이 각본 기사를 배경으로 덮어쓴다.
    """
    rows: list[RawNewsWrite] = []
    for index in range(count):
        ticker, company = _BACKGROUND[index % len(_BACKGROUND)]
        headline = _HEADLINES[index % len(_HEADLINES)].format(company=company)
        at = published_from + timedelta(minutes=7 * index)
        rows.append(
            RawNewsWrite(
                article_id=1000 + index,
                ticker=ticker,
                trade_date=at.date(),
                headline=headline,
                source=_SOURCE,
                url=f"https://demo.invalid/wire/{1000 + index}",
                published_at=at,
            )
        )
    return tuple(rows)


def background_filings(*, trade_date: date, count: int = 17) -> tuple[RawDisclosureWrite, ...]:
    """Build routine filings so the disclosure job reports real volume."""
    rows: list[RawDisclosureWrite] = []
    for index in range(count):
        ticker, company = _BACKGROUND[index % len(_BACKGROUND)]
        form_type, is_hard = _FORMS[index % len(_FORMS)]
        rows.append(
            RawDisclosureWrite(
                filing_no=f"demo-{trade_date.isoformat()}-{index:04d}",
                trade_date=trade_date,
                ticker=ticker,
                cik=f"{9000000 + index:010d}",
                form_type=form_type,
                company_name=company,
                source_ref=f"https://demo.invalid/filing/{index:04d}",
                event_type=None,
                is_hard_event=is_hard,
            )
        )
    return tuple(rows)
