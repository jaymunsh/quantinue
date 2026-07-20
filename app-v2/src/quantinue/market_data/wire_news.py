"""Press-release wire RSS: the headlines that can earn a vote (roadmap R11).

Alpaca 뉴스는 전부 benzinga(gray 0.50)라 투표권이 없다. 와이어 3사는
``news_trust_policy.yaml``에서 ``allow``(0.95)다 — 실적·M&A·가이던스 같은
실제 사건이 여기서 나온다. 이 어댑터는 그 원문 피드를 줍는다.

티커 추출은 두 층이고 순서가 신뢰도다:
1. **구조화 카테고리**(GlobeNewswire): ``<category domain=".../rss/stock">
   Nasdaq:DJT</category>``. 발행사가 직접 단 태그라 추출이 아니라 낭독이다.
2. **산문 패턴**(PRNewswire 등): 본문의 ``(NYSE: PLNT)`` 관례. 미국 거래소
   세그먼트만 읽고, 패턴 밖 매칭은 하지 않는다 — 못 찾으면 그 기사는
   버린다(회사명 유사도 매칭 같은 오탐 기계를 만들지 않는다).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

import httpx2

from quantinue.db.domain_records import RawNewsWrite

if TYPE_CHECKING:
    from datetime import date

NEW_YORK: Final = ZoneInfo("America/New_York")
# 산문 관례: "(NYSE: PLNT)" · "(Nasdaq: FDMT, 4DMT or the Company)" ·
# "(NYSE: EVEX, EVEXW; B3: EVEB31)". 괄호 안을 세미콜론으로 가르면 세그먼트마다
# "거래소: 심볼들"이고, 미국 거래소 세그먼트만 읽는다.
_PAREN: Final = re.compile(r"\(([^()]{2,120})\)")
_US_EXCHANGES: Final = ("nasdaq", "nyse", "nyse american", "amex")
_TICKER: Final = re.compile(r"^[A-Z]{1,5}(?:[.][A-Z])?$")
_STOCK_CATEGORY_DOMAIN: Final = "rss/stock"


def _stable_article_id(guid: str) -> int:
    """Derive a stable positive id from the feed guid.

    Alpaca의 기사 id는 API가 주지만 RSS에는 정수 id가 없다. PK가
    ``(article_id, ticker)``이므로 실행마다 같은 guid가 같은 id로 떨어져야
    멱등이 성립한다 — 해시 앞 62비트를 쓴다(BIGINT 양수 범위).
    """
    return int.from_bytes(sha256(guid.encode()).digest()[:8], "big") >> 2


def extract_prose_tickers(text: str) -> tuple[str, ...]:
    """Read US-exchange tickers out of the press-release convention only."""
    found: list[str] = []
    for group in _PAREN.findall(text):
        for segment in group.split(";"):
            exchange, _, symbols = segment.partition(":")
            if exchange.strip().lower() not in _US_EXCHANGES:
                continue
            for raw in symbols.split(","):
                # "FDMT, 4DMT or the Company" 같은 산문 꼬리는 티커 알파벳
                # 검증이 걸러낸다 — 패턴 밖 매칭 금지의 실체가 이 검증이다.
                candidate = raw.strip().split()[0] if raw.strip() else ""
                if _TICKER.match(candidate) and candidate not in found:
                    found.append(candidate)
    return tuple(found)


def _category_tickers(item: ET.Element) -> tuple[str, ...]:
    """Read the publisher-tagged stock categories, if the feed has them."""
    found: list[str] = []
    for category in item.findall("category"):
        if _STOCK_CATEGORY_DOMAIN not in (category.get("domain") or ""):
            continue
        _, _, symbol = (category.text or "").partition(":")
        candidate = symbol.strip().upper()
        if _TICKER.match(candidate) and candidate not in found:
            found.append(candidate)
    return tuple(found)


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


@dataclass(frozen=True, slots=True)
class WireFeed:
    """One wire's RSS endpoint and the source name the trust policy grades."""

    url: str
    source: str


@dataclass(frozen=True, slots=True)
class WireRssSource:
    """Collect company press releases from the free wire RSS feeds."""

    feeds: tuple[WireFeed, ...]
    transport: httpx2.AsyncBaseTransport | None = None
    timeout_seconds: float = 30.0

    async def articles(self, session: date, until: date) -> tuple[RawNewsWrite, ...]:
        """Return every ticker-tagged release in the session-to-run window.

        창 규칙은 Alpaca 어댑터와 같다(세션 00:00 ~ 실행일+1 00:00, 뉴욕) —
        주말 기사를 다음 실행이 다시 줍지 않기 때문이고, 겹침은 (기사, 티커)
        키가 흡수한다. RSS는 최신 ~20건짜리 창이라 페이지네이션이 없다:
        일 1회 주기로 충분히 덮이고, 놓친 과거는 소급할 수 없음을 안다.
        """
        window_start = datetime.combine(session, time(), tzinfo=NEW_YORK)
        window_end = datetime.combine(until + timedelta(days=1), time(), tzinfo=NEW_YORK)
        rows: list[RawNewsWrite] = []
        async with httpx2.AsyncClient(
            transport=self.transport,
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Quantinue/1.0"},
            follow_redirects=True,
        ) as client:
            for feed in self.feeds:
                payload = (await client.get(feed.url)).raise_for_status().text
                rows.extend(self._parse(feed, payload, window_start, window_end, session))
        return tuple(rows)

    def _parse(
        self,
        feed: WireFeed,
        payload: str,
        window_start: datetime,
        window_end: datetime,
        session: date,
    ) -> list[RawNewsWrite]:
        rows: list[RawNewsWrite] = []
        for item in ET.fromstring(payload).iter("item"):  # noqa: S314 - 설정된 공개 피드만(기존 RSS 관행)
            guid = _text(item, "guid") or _text(item, "link")
            headline = _text(item, "title")
            if not guid or not headline:
                continue
            published = _published(item)
            if published is None or not window_start <= published < window_end:
                continue
            tickers = _category_tickers(item) or extract_prose_tickers(
                f"{headline} {_text(item, 'description')}"
            )
            rows.extend(
                RawNewsWrite(
                    article_id=_stable_article_id(guid),
                    ticker=ticker,
                    trade_date=session,
                    headline=headline,
                    source=feed.source,
                    url=_text(item, "link") or guid,
                    published_at=published,
                )
                for ticker in tickers
            )
        return rows


def _published(item: ET.Element) -> datetime | None:
    raw = _text(item, "pubDate")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        # 날짜를 못 읽은 기사를 "지금"으로 두면 창 필터가 무의미해진다 —
        # 버리는 쪽이 정직하다.
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def default_wire_feeds() -> tuple[WireFeed, ...]:
    """Return the free, keyless wires the trust policy already grades allow.

    businesswire는 넣지 않았다 — 공개 RSS 인덱스가 UA에 따라 차단되는 것을
    실측했고(2026-07-20), 불안정한 피드 하나가 잡을 매일 실패시키는 것보다
    안정적인 둘로 시작하는 쪽이 낫다. 추가는 이 튜플에 한 줄이다.
    """
    return (
        WireFeed(
            url=(
                "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
                "GlobeNewswire%20-%20News%20about%20Public%20Companies"
            ),
            source="globenewswire.com",
        ),
        WireFeed(
            url="https://www.prnewswire.com/rss/news-releases-list.rss",
            source="prnewswire.com",
        ),
    )
