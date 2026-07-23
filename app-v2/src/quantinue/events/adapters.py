"""Adapters from existing SEC, Alpaca, and wire providers to event pages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from quantinue.events.ingestion import EventDocument, EventPage, SourceCursor

if TYPE_CHECKING:
    from quantinue.db.domain_records import RawDisclosureWrite, RawNewsWrite


class DisclosureBatchProvider(Protocol):
    """Existing whole-market SEC provider contract."""

    async def filings(self, trade_date: date) -> tuple[RawDisclosureWrite, ...]:
        """Return filings for one SEC business date."""
        ...


class NewsBatchProvider(Protocol):
    """Existing news and wire provider contract."""

    async def articles(
        self, session: date, until: date
    ) -> tuple[RawNewsWrite, ...]:
        """Return ticker-tagged articles inside the requested date window."""
        ...


def _start_date(cursor: SourceCursor | None, overlap: timedelta, now: datetime) -> date:
    if cursor is None:
        return now.date()
    return (datetime.fromisoformat(cursor) - overlap).date()


@dataclass(frozen=True, slots=True)
class SecEventSourceAdapter:
    """Incremental page boundary backed by ``SecDailyIndexSource``."""

    provider: DisclosureBatchProvider
    now: datetime

    async def fetch_page(
        self,
        cursor: SourceCursor | None,
        page_token: str | None,
        overlap: timedelta,
    ) -> EventPage:
        """Collect SEC rows without fetching the filing document URLs."""
        if page_token is not None:
            raise RuntimeError(page_token)
        rows = await self.provider.filings(_start_date(cursor, overlap, self.now))
        documents = tuple(
            EventDocument(
                provider_id=row.filing_no,
                source_url=row.source_ref,
                published_at=datetime.combine(row.trade_date, datetime.min.time(), self.now.tzinfo),
                raw_text=json.dumps(
                    {
                        "cik": row.cik,
                        "company_name": row.company_name,
                        "form_type": row.form_type,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                ticker=row.ticker,
                event_type=row.event_type or "disclosure",
                source_sequence=row.filing_no,
            )
            for row in rows
        )
        return EventPage(documents, None, self.now.isoformat())


@dataclass(frozen=True, slots=True)
class NewsEventSourceAdapter:
    """Incremental page boundary backed by Alpaca or wire batch providers."""

    provider: NewsBatchProvider
    now: datetime
    event_type: str = "news"

    async def fetch_page(
        self,
        cursor: SourceCursor | None,
        page_token: str | None,
        overlap: timedelta,
    ) -> EventPage:
        """Collect provider rows while treating URLs and headlines only as data."""
        if page_token is not None:
            raise RuntimeError(page_token)
        rows = await self.provider.articles(
            _start_date(cursor, overlap, self.now),
            self.now.date(),
        )
        documents = tuple(
            EventDocument(
                provider_id=str(row.article_id),
                source_url=row.url,
                published_at=row.published_at,
                raw_text=json.dumps(
                    {"headline": row.headline, "source": row.source},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                ticker=row.ticker,
                event_type=self.event_type,
                source_sequence=f"{row.published_at.isoformat()}:{row.article_id}",
            )
            for row in rows
        )
        return EventPage(documents, None, self.now.isoformat())
