"""PostgreSQL persistence and exactly-once cache boundary for event evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from quantinue.events.evidence import (
    DIRECT_DOCUMENT_CHARS,
    MAX_SUMMARY_CHARS,
    EvidenceDocumentError,
    EvidenceErrorCode,
    EvidencePack,
    RawEvidenceDocument,
    build_evidence_spans,
    render_strategy_evidence,
    summary_prompt,
    summary_prompt_identity,
    summary_task,
)
from quantinue.llm.prompts import load_system_prompt

if TYPE_CHECKING:
    from quantinue.events.routing import AcceptedRoute
    from quantinue.llm.provider import LlmAnalyzer


class _EvidenceDocumentRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    event_id: int
    raw_version_id: int
    content_hash: str
    source_name: str
    source_document_id: str
    source_url: str
    source_sequence: str
    ticker: str
    normalized_text: str


class _SummaryRow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    summary_text: str


class PostgresEventEvidenceRepository:
    """Persist citation spans and serialize summary creation by cache key."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy PostgreSQL engine for the event ledger."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def close(self) -> None:
        """Dispose all pooled database connections."""
        await self._engine.dispose()

    async def prepare(
        self,
        route: AcceptedRoute,
        analyzer: LlmAnalyzer,
        *,
        summary_prompt_version: str | None = None,
        summary_timeout_seconds: float = 30.0,
    ) -> EvidencePack:
        """Build one routed event's durable bounded evidence pack."""
        with anyio.CancelScope(shield=True):
            async with self._engine.begin() as connection:
                document = await self._document(connection, route)
                spans = build_evidence_spans(document)
                for span in spans:
                    _ = await connection.execute(
                        text(
                            """
                        INSERT INTO tb_event_evidence_pack
                          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
                        VALUES
                          (:event_id, :raw_version_id, :start_offset, :end_offset, :quote_hash)
                        ON CONFLICT
                          (event_id, raw_version_id, start_offset, end_offset)
                        DO NOTHING
                        """
                        ),
                        {
                            "event_id": document.event_id,
                            "raw_version_id": document.raw_version_id,
                            "start_offset": span.start_offset,
                            "end_offset": span.end_offset,
                            "quote_hash": span.quote_hash,
                        },
                    )
                summary = await self._summary(
                    connection,
                    document,
                    analyzer,
                    summary_prompt_version=summary_prompt_version,
                    summary_timeout_seconds=summary_timeout_seconds,
                )
            return EvidencePack(
                document=document,
                spans=spans,
                summary=summary,
                strategy_input=render_strategy_evidence(document, spans, summary),
            )
        raise EvidenceDocumentError(EvidenceErrorCode.INTERRUPTED)

    async def _document(
        self,
        connection: AsyncConnection,
        route: AcceptedRoute,
    ) -> RawEvidenceDocument:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT event.event_id, event.raw_version_id,
                           version.content_hash, event.source_name,
                           document.source_document_id, document.source_url,
                           event.source_sequence, event.payload->>'ticker' AS ticker,
                           version.normalized_text
                    FROM tb_normalized_event AS event
                    JOIN tb_event_raw_version AS version USING (raw_version_id)
                    JOIN tb_event_raw_document AS document USING (document_id)
                    JOIN tb_event_processing_receipt AS receipt
                      ON receipt.event_id = event.event_id
                     AND receipt.persona LIKE 'routing:accepted:%'
                    WHERE event.event_id = :event_id
                      AND event.raw_version_id = :raw_version_id
                    """
                    ),
                    {
                        "event_id": route.event_id,
                        "raw_version_id": route.raw_version_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise EvidenceDocumentError(EvidenceErrorCode.UNAVAILABLE)
        parsed = _EvidenceDocumentRow.model_validate(dict(row))
        document = RawEvidenceDocument(
            event_id=parsed.event_id,
            raw_version_id=parsed.raw_version_id,
            content_hash=parsed.content_hash,
            source_name=parsed.source_name,
            source_document_id=parsed.source_document_id,
            source_url=parsed.source_url,
            source_sequence=parsed.source_sequence,
            ticker=parsed.ticker,
            normalized_text=parsed.normalized_text,
        )
        if document.content_hash != route.content_hash:
            raise EvidenceDocumentError(EvidenceErrorCode.HASH_MISMATCH)
        return document

    async def _summary(
        self,
        connection: AsyncConnection,
        document: RawEvidenceDocument,
        analyzer: LlmAnalyzer,
        *,
        summary_prompt_version: str | None,
        summary_timeout_seconds: float,
    ) -> str | None:
        if len(document.normalized_text) <= DIRECT_DOCUMENT_CHARS:
            return None
        task = summary_task(document.source_name)
        prompt = summary_prompt(document)
        model = analyzer.maximum_usage(task, prompt).model
        prompt_version = (
            load_system_prompt(task.value).version
            if summary_prompt_version is None
            else summary_prompt_version
        )
        prompt_identity = summary_prompt_identity(task, prompt_version)
        cache_key = f"{document.content_hash}:{model}:{prompt_identity}"
        _ = await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": cache_key},
        )
        cached = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT summary_text
                    FROM tb_event_summary_cache
                    WHERE content_hash = :content_hash
                      AND model = :model
                      AND prompt_version = :prompt_identity
                    """
                    ),
                    {
                        "content_hash": document.content_hash,
                        "model": model,
                        "prompt_identity": prompt_identity,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if cached is not None:
            return _SummaryRow.model_validate(dict(cached)).summary_text
        summary = ""
        with anyio.fail_after(summary_timeout_seconds):
            result = await analyzer.analyze(task, prompt)
        summary = result.reason.strip()
        if not summary:
            raise EvidenceDocumentError(EvidenceErrorCode.EMPTY_SUMMARY)
        if len(summary) > MAX_SUMMARY_CHARS:
            raise EvidenceDocumentError(EvidenceErrorCode.OVERSIZED_SUMMARY)
        if result.metadata.model != model:
            raise EvidenceDocumentError(EvidenceErrorCode.MODEL_MISMATCH)
        if result.metadata.prompt_version != prompt_version:
            raise EvidenceDocumentError(EvidenceErrorCode.PROMPT_MISMATCH)
        with anyio.CancelScope(shield=True):
            _ = await connection.execute(
                text(
                    """
                    INSERT INTO tb_event_summary_cache
                      (raw_version_id, content_hash, normalized_length,
                       model, prompt_version, summary_text)
                    VALUES
                      (:raw_version_id, :content_hash, :normalized_length,
                       :model, :prompt_version, :summary_text)
                    """
                ),
                {
                    "raw_version_id": document.raw_version_id,
                    "content_hash": document.content_hash,
                    "normalized_length": len(document.normalized_text),
                    "model": model,
                    "prompt_version": prompt_identity,
                    "summary_text": summary,
                },
            )
        if not summary:
            raise EvidenceDocumentError(EvidenceErrorCode.INTERRUPTED)
        return summary
