"""Roadmap R11: wire press releases — the headlines that can earn a vote."""

from __future__ import annotations

from datetime import date

import httpx2
import pytest

from quantinue.market_data.wire_news import (
    WireFeed,
    WireRssSource,
    extract_prose_tickers,
)

_SESSION = date(2026, 7, 17)
_RUN_DAY = date(2026, 7, 20)

# 실 피드에서 그대로 가져온 형태다(2026-07-20 실측) — 지어낸 XML이 아니다.
_GNW_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <guid isPermaLink="true">https://example.invalid/gnw/1</guid>
    <link>https://example.invalid/gnw/1</link>
    <category domain="https://www.globenewswire.com/rss/stock">Nasdaq:DJT</category>
    <category domain="https://www.globenewswire.com/rss/ISIN">US25400Q1058</category>
    <title>Trump Media Settles Legal Disputes</title>
    <description><![CDATA[SARASOTA, Fla. (Nasdaq, NYSE Texas: DJT)]]></description>
    <pubDate>Sun, 19 Jul 2026 13:00:00 +0000</pubDate>
  </item>
  <item>
    <guid isPermaLink="true">https://example.invalid/gnw/2</guid>
    <link>https://example.invalid/gnw/2</link>
    <title>Municipal Bond Notice Without Any Stock Tag</title>
    <description><![CDATA[No ticker anywhere.]]></description>
    <pubDate>Sun, 19 Jul 2026 14:00:00 +0000</pubDate>
  </item>
  <item>
    <guid isPermaLink="true">https://example.invalid/gnw/3</guid>
    <link>https://example.invalid/gnw/3</link>
    <category domain="https://www.globenewswire.com/rss/stock">Nasdaq:OLD</category>
    <title>Stale Release Outside The Window</title>
    <description><![CDATA[old]]></description>
    <pubDate>Wed, 01 Jul 2026 14:00:00 +0000</pubDate>
  </item>
</channel></rss>"""

_PRN_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <guid>https://example.invalid/prn/1</guid>
    <link>https://example.invalid/prn/1</link>
    <title>Planet Fitness Reports Results</title>
    <description><![CDATA[HAMPTON, N.H. Planet Fitness, Inc.
      (NYSE: PLNT) today reported.]]></description>
    <pubDate>Sun, 19 Jul 2026 23:00:00 +0000</pubDate>
  </item>
</channel></rss>"""


def _source(gnw: str = _GNW_FEED, prn: str = _PRN_FEED) -> WireRssSource:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = gnw if "globenewswire" in request.url.host else prn
        return httpx2.Response(200, text=body, request=request)

    return WireRssSource(
        feeds=(
            WireFeed(url="https://www.globenewswire.com/feed", source="globenewswire.com"),
            WireFeed(url="https://www.prnewswire.com/feed", source="prnewswire.com"),
        ),
        transport=httpx2.MockTransport(handler),
    )


@pytest.mark.anyio
async def test_publisher_tagged_tickers_are_read_not_guessed() -> None:
    """GNW의 구조화 카테고리는 발행사가 단 태그다 — 추출이 아니라 낭독."""
    # When
    rows = await _source().articles(_SESSION, _RUN_DAY)

    # Then
    gnw = [row for row in rows if row.source == "globenewswire.com"]
    assert [row.ticker for row in gnw] == ["DJT"]
    assert gnw[0].headline == "Trump Media Settles Legal Disputes"
    assert gnw[0].trade_date == _SESSION


@pytest.mark.anyio
async def test_prose_convention_is_read_for_feeds_without_tags() -> None:
    # When
    rows = await _source().articles(_SESSION, _RUN_DAY)

    # Then
    prn = [row for row in rows if row.source == "prnewswire.com"]
    assert [row.ticker for row in prn] == ["PLNT"]


@pytest.mark.anyio
async def test_a_release_without_any_ticker_is_dropped() -> None:
    """티커 없는 보도자료는 종목 뉴스가 아니다 — 회사명 유사도 매칭은 없다."""
    # When
    rows = await _source().articles(_SESSION, _RUN_DAY)

    # Then
    assert all("Municipal" not in row.headline for row in rows)


@pytest.mark.anyio
async def test_releases_outside_the_window_are_dropped() -> None:
    # When
    rows = await _source().articles(_SESSION, _RUN_DAY)

    # Then
    assert all(row.ticker != "OLD" for row in rows)


@pytest.mark.anyio
async def test_the_same_guid_lands_on_the_same_article_id_every_run() -> None:
    """멱등의 근거 — PK (article_id, ticker)가 재수집 겹침을 흡수하려면."""
    # When
    first = await _source().articles(_SESSION, _RUN_DAY)
    second = await _source().articles(_SESSION, _RUN_DAY)

    # Then
    assert [row.article_id for row in first] == [row.article_id for row in second]
    assert all(row.article_id > 0 for row in first)


def test_prose_extraction_reads_only_us_exchange_segments() -> None:
    """B3(브라질) 세그먼트와 산문 꼬리는 걸러진다 — 실측한 실물 관례다."""
    assert extract_prose_tickers("(NYSE: EVEX, EVEXW; B3: EVEB31)") == ("EVEX", "EVEXW")
    assert extract_prose_tickers("(Nasdaq: FDMT, 4DMT or the Company)") == ("FDMT",)
    assert extract_prose_tickers("(KOSDAQ: 950160)") == ()
    assert extract_prose_tickers("no convention here") == ()
