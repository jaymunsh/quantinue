"""Scripted demo event source: fixed good/bad articles through the real seam."""

from datetime import UTC, date, datetime, timedelta

import pytest

from quantinue.demo.scripted_events import (
    ScriptedHeadline,
    ScriptedNewsProvider,
    scenario_articles,
)
from quantinue.events.adapters import NewsEventSourceAdapter

_GOOD_AT = datetime(2026, 7, 24, 14, 45, tzinfo=UTC)
_BAD_AT = datetime(2026, 7, 24, 15, 30, tzinfo=UTC)


def _provider() -> ScriptedNewsProvider:
    return ScriptedNewsProvider(
        articles=scenario_articles(
            good=ScriptedHeadline(
                ticker="GOODCO",
                headline="GOODCO wins multi-year supply contract",
                at=_GOOD_AT,
            ),
            bad=ScriptedHeadline(
                ticker="BADCO",
                headline="BADCO withdraws full-year guidance",
                at=_BAD_AT,
            ),
        )
    )


class TestScriptedNewsProvider:
    @pytest.mark.anyio
    async def test_returns_only_articles_inside_the_window(self) -> None:
        provider = _provider()
        both = await provider.articles(date(2026, 7, 24), date(2026, 7, 24))
        none = await provider.articles(date(2026, 7, 25), date(2026, 7, 26))
        assert [row.ticker for row in both] == ["GOODCO", "BADCO"]
        assert none == ()

    @pytest.mark.anyio
    async def test_same_scenario_yields_identical_rows(self) -> None:
        window = (date(2026, 7, 24), date(2026, 7, 24))
        assert await _provider().articles(*window) == await _provider().articles(*window)

    @pytest.mark.anyio
    async def test_article_ids_are_stable_dedup_keys(self) -> None:
        # 재수집 시 신규 0건은 이 provider_id의 안정성에 달려 있다 —
        # 수집 경로의 dedup은 (source, provider_id)로 같은 원문을 접는다.
        (good, bad) = await _provider().articles(date(2026, 7, 24), date(2026, 7, 24))
        (good_again, _) = await _provider().articles(date(2026, 7, 24), date(2026, 7, 24))
        assert good.article_id == good_again.article_id
        assert good.article_id != bad.article_id


class TestThroughRealAdapterSeam:
    @pytest.mark.anyio
    async def test_adapter_produces_deterministic_event_documents(self) -> None:
        now = datetime(2026, 7, 24, 16, 0, tzinfo=UTC)
        adapter = NewsEventSourceAdapter(provider=_provider(), now=now)
        first = await adapter.fetch_page(None, None, timedelta(days=1))
        second = await adapter.fetch_page(None, None, timedelta(days=1))
        assert first.documents == second.documents
        assert [doc.ticker for doc in first.documents] == ["GOODCO", "BADCO"]
        assert all(doc.provider_id for doc in first.documents)
