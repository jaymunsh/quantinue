"""Relevance decides who is eligible; source trust decides who represents.

Ranking purely by keyword relevance let a gray-grade outlet win simply for
repeating the ticker more often. Relevance is now a gate, and among the items
that pass, the most trustworthy source is the one the model reads.
"""

from datetime import UTC, datetime, timedelta

from quantinue.market_data.models import NewsItem, Provenance, TickerNewsQuery
from quantinue.roles.role_06_news_analysis.selection import select_ticker_news

NOW = datetime(2026, 7, 14, 3, 0, tzinfo=UTC)
QUERY = TickerNewsQuery(ticker="NVDA", company_name="NVIDIA Corporation")


def _news(
    title: str,
    url: str,
    *,
    snippet: str = "NVIDIA demand commentary",
    confidence: float = 0.9,
    published_at: datetime = NOW,
) -> NewsItem:
    return NewsItem(
        title=title,
        snippet=snippet,
        url=url,
        guid=url,
        published_at=published_at,
        provenance=Provenance(
            source="rss",
            source_ref=url,
            observed_at=NOW,
            captured_at=NOW,
            confidence=confidence,
            execution_id="run-news",
        ),
    )


def test_a_trusted_source_represents_over_a_more_keyword_dense_gray_one() -> None:
    # Given: the gray item mentions NVDA in both title and snippet (higher
    # relevance), the trusted item only in the title.
    gray = _news("NVDA NVIDIA everywhere", "https://unknown-blog.test/a", snippet="NVDA NVIDIA")
    trusted = _news("NVDA outlook raised", "https://www.reuters.com/b", snippet="analyst note")

    result = select_ticker_news((gray, trusted), QUERY)

    assert result.selected is not None
    assert "reuters.com" in result.selected.item.url


def test_relevance_remains_a_hard_gate() -> None:
    # A trusted source that is not about this company cannot represent it.
    irrelevant = _news("Markets drift", "https://www.reuters.com/x", snippet="broad market wrap")

    result = select_ticker_news((irrelevant,), QUERY)

    assert result.selected is None


def test_confidence_breaks_ties_within_the_same_grade() -> None:
    low = _news("NVDA outlook", "https://www.reuters.com/low", confidence=0.5)
    high = _news("NVDA outlook", "https://www.reuters.com/high", confidence=0.95)

    result = select_ticker_news((low, high), QUERY)

    assert result.selected is not None
    assert result.selected.item.url.endswith("/high")


def test_recency_breaks_a_full_tie() -> None:
    older = _news("NVDA outlook", "https://www.reuters.com/older", published_at=NOW - timedelta(1))
    newer = _news("NVDA outlook", "https://www.reuters.com/newer", published_at=NOW)

    result = select_ticker_news((older, newer), QUERY)

    assert result.selected is not None
    assert result.selected.item.url.endswith("/newer")


def test_every_fetched_item_is_still_preserved() -> None:
    items = (
        _news("NVDA one", "https://www.reuters.com/1"),
        _news("Unrelated", "https://www.reuters.com/2", snippet="nothing here"),
    )

    result = select_ticker_news(items, QUERY)

    assert result.fetched_count == 2
    assert len(result.items) == 2
