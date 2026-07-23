"""Transactional incremental ingestion into the immutable event ledger."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, NewType, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from quantinue.events.repository_queries import (
    count_documents,
    integer_value,
    latest_raw_text,
    string_value,
)

if TYPE_CHECKING:
    from datetime import datetime, timedelta

SourceCursor = NewType("SourceCursor", str)


@dataclass(frozen=True, slots=True)
class EventDocument:
    """One provider document parsed at the provider boundary."""

    provider_id: str
    source_url: str
    published_at: datetime
    raw_text: str
    ticker: str
    event_type: str
    source_sequence: str


@dataclass(frozen=True, slots=True)
class EventPage:
    """A complete provider page and its durable checkpoint."""

    documents: tuple[EventDocument, ...]
    next_page_token: str | None
    checkpoint: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Observable totals from one successful provider traversal."""

    pages_committed: int
    documents_seen: int


class IncrementalEventSource(Protocol):
    """Provider boundary that receives the durable cursor and overlap window."""

    async def fetch_page(
        self,
        cursor: SourceCursor | None,
        page_token: str | None,
        overlap: timedelta,
    ) -> EventPage:
        """Fetch one complete page without following document URLs."""
        ...


class PaginationLoopError(RuntimeError):
    """A provider repeated a token instead of making forward progress."""


class PostgresEventIngestionRepository:
    """Page-transaction repository for the immutable event tables."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy PostgreSQL engine."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        """Dispose all pooled connections."""
        await self._engine.dispose()

    async def cursor(self, source_name: str) -> SourceCursor | None:
        """Read the last fully committed provider checkpoint."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT cursor_value AS value FROM tb_event_source_cursor
                    WHERE source_name = :source_name
                    """
                ),
                {"source_name": source_name},
            )
            row = result.mappings().one_or_none()
        return None if row is None else SourceCursor(string_value(row))

    async def commit_page(
        self,
        source_name: str,
        page: EventPage,
    ) -> None:
        """Commit documents, versions, receipts, and cursor atomically."""
        async with self._engine.begin() as connection:
            for document in page.documents:
                result = await connection.execute(
                    text(
                        """
                        INSERT INTO tb_event_raw_document
                          (source_name, source_document_id, source_url, published_at)
                        VALUES (:source_name, :provider_id, :source_url, :published_at)
                        ON CONFLICT (source_name, source_document_id) DO NOTHING
                        RETURNING document_id AS value
                        """
                    ),
                    {
                        "source_name": source_name,
                        "provider_id": document.provider_id,
                        "source_url": document.source_url,
                        "published_at": document.published_at,
                    },
                )
                row = result.mappings().one_or_none()
                document_id = (
                    None if row is None else integer_value(row)
                )
                if document_id is None:
                    result = await connection.execute(
                        text(
                            """
                            SELECT document_id AS value FROM tb_event_raw_document
                            WHERE source_name = :source_name
                              AND source_document_id = :provider_id
                            """
                        ),
                        {
                            "source_name": source_name,
                            "provider_id": document.provider_id,
                        },
                    )
                    document_id = integer_value(result.mappings().one())
                content_hash = sha256(document.raw_text.encode()).hexdigest()
                result = await connection.execute(
                    text(
                        """
                        INSERT INTO tb_event_raw_version
                          (document_id, version_no, content_hash, raw_text,
                           normalized_text, normalized_length)
                        SELECT :document_id, coalesce(max(version_no), 0) + 1,
                               :content_hash, :raw_text, :raw_text, char_length(:raw_text)
                        FROM tb_event_raw_version
                        WHERE document_id = :document_id
                        ON CONFLICT (document_id, content_hash) DO NOTHING
                        RETURNING raw_version_id AS value
                        """
                    ),
                    {
                        "document_id": document_id,
                        "content_hash": content_hash,
                        "raw_text": document.raw_text,
                    },
                )
                row = result.mappings().one_or_none()
                raw_version_id = (
                    None if row is None else integer_value(row)
                )
                if raw_version_id is None:
                    result = await connection.execute(
                        text(
                            """
                            SELECT raw_version_id AS value FROM tb_event_raw_version
                            WHERE document_id = :document_id AND content_hash = :content_hash
                            """
                        ),
                        {"document_id": document_id, "content_hash": content_hash},
                    )
                    raw_version_id = integer_value(result.mappings().one())
                event_key = (
                    f"{source_name}:{document.provider_id}:{document.ticker}:{content_hash}"
                )
                result = await connection.execute(
                    text(
                        """
                        INSERT INTO tb_normalized_event
                          (raw_version_id, event_key, source_name, source_sequence,
                           event_type, occurred_at, payload)
                        VALUES (:raw_version_id, :event_key, :source_name,
                                :source_sequence, :event_type, :occurred_at,
                                jsonb_build_object('ticker', CAST(:ticker AS text)))
                        ON CONFLICT (event_key) DO NOTHING
                        RETURNING event_id AS value
                        """
                    ),
                    {
                        "raw_version_id": raw_version_id,
                        "event_key": event_key,
                        "source_name": source_name,
                        "source_sequence": (
                            f"{document.source_sequence}:{document.ticker}:{content_hash}"
                        ),
                        "event_type": document.event_type,
                        "occurred_at": document.published_at,
                        "ticker": document.ticker,
                    },
                )
                row = result.mappings().one_or_none()
                event_id = None if row is None else integer_value(row)
                if event_id is None:
                    result = await connection.execute(
                        text(
                            """
                            SELECT event_id AS value FROM tb_normalized_event
                            WHERE event_key = :key
                            """
                        ),
                        {"key": event_key},
                    )
                    event_id = integer_value(result.mappings().one())
                _ = await connection.execute(
                    text(
                        """
                        INSERT INTO tb_event_processing_receipt
                          (event_id, ticker, persona, status, completed_at)
                        VALUES (:event_id, :ticker, 'ingestion', 'processed', now())
                        ON CONFLICT (event_id, ticker, persona) DO NOTHING
                        """
                    ),
                    {"event_id": event_id, "ticker": document.ticker},
                )
            _ = await connection.execute(
                text(
                    """
                    INSERT INTO tb_event_source_cursor
                      (source_name, cursor_value, checkpoint_at)
                    VALUES (:source_name, :checkpoint, now())
                    ON CONFLICT (source_name) DO UPDATE
                    SET cursor_value = excluded.cursor_value,
                        checkpoint_at = excluded.checkpoint_at,
                        updated_at = now()
                    WHERE tb_event_source_cursor.cursor_value < excluded.cursor_value
                    """
                ),
                {"source_name": source_name, "checkpoint": page.checkpoint},
            )

    async def count_documents(self, source_name: str) -> int:
        """Count stable provider documents for verification."""
        return await count_documents(self._engine, source_name)

    async def raw_text(self, source_name: str, provider_id: str) -> str | None:
        """Read the latest immutable raw version for verification."""
        return await latest_raw_text(self._engine, source_name, provider_id)


async def ingest_incrementally(
    source_name: str,
    source: IncrementalEventSource,
    repository: PostgresEventIngestionRepository,
    overlap: timedelta,
) -> IngestionResult:
    """Traverse pages, rejecting loops before committing the repeated page."""
    cursor = await repository.cursor(source_name)
    page_token: str | None = None
    seen_tokens: set[str] = set()
    pages_committed = 0
    documents_seen = 0
    while True:
        page = await source.fetch_page(cursor, page_token, overlap)
        next_token = page.next_page_token
        if next_token is not None and (
            next_token == page_token or next_token in seen_tokens
        ):
            raise PaginationLoopError(next_token)
        await repository.commit_page(source_name, page)
        pages_committed += 1
        documents_seen += len(page.documents)
        if next_token is None:
            return IngestionResult(pages_committed, documents_seen)
        seen_tokens.add(next_token)
        page_token = next_token
