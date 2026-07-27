"""Scripted news provider feeding the real event-ingestion seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quantinue.db.domain_records import RawNewsWrite

if TYPE_CHECKING:
    from datetime import date, datetime

# 각본 기사임이 URL만 봐도 드러나게 예약된 무효 도메인을 쓴다 — 실존 매체
# URL을 흉내 내면 촬영본이 실제 보도로 오인될 수 있다(demo-video-plan.md §1).
_DEMO_URL = "https://demo.invalid/scripted-article"
_DEMO_SOURCE = "demo:scripted-news"


@dataclass(frozen=True, slots=True)
class ScriptedHeadline:
    """One scripted article: which ticker hears what, and when."""

    ticker: str
    headline: str
    at: datetime


def scenario_articles(
    *, good: ScriptedHeadline, bad: ScriptedHeadline
) -> tuple[RawNewsWrite, ...]:
    """Build the fixed S3(호재)·S4(악재) article pair.

    article_id를 1·2로 고정하는 것이 재수집 dedup의 핵심이다 — 수집 경로는
    (source, provider_id)로 같은 원문을 접으므로, 같은 각본을 다시 넣으면
    신규 0건이어야 한다(demo-video-plan.md §4-3 완료 기준).
    """
    return tuple(
        RawNewsWrite(
            article_id=article_id,
            ticker=item.ticker.upper(),
            trade_date=item.at.date(),
            headline=item.headline,
            source=_DEMO_SOURCE,
            url=f"{_DEMO_URL}/{article_id}",
            published_at=item.at,
        )
        for article_id, item in ((1, good), (2, bad))
    )


class ScriptedNewsProvider:
    """`NewsBatchProvider` that replays a fixed article list.

    기존 `NewsEventSourceAdapter` 이음새에 그대로 꽂혀 수집·정규화·라우팅·
    evidence 경로를 전부 실제 코드로 통과한다 — 데모가 대체하는 것은
    "언제 어떤 기사가 오는가"뿐이다.
    """

    def __init__(self, *, articles: tuple[RawNewsWrite, ...]) -> None:
        """Bind the immutable scripted article list."""
        self._articles = articles

    async def articles(self, session: date, until: date) -> tuple[RawNewsWrite, ...]:
        """Return scripted articles whose trade date falls inside the window."""
        return tuple(
            row for row in self._articles if session <= row.trade_date <= until
        )
