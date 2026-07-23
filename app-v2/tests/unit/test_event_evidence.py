from __future__ import annotations

from hashlib import sha256

import pytest

from quantinue.events.evidence import (
    DIRECT_DOCUMENT_CHARS,
    MAX_DOCUMENT_CHARS,
    EvidenceDocumentError,
    RawEvidenceDocument,
    build_evidence_spans,
    render_strategy_evidence,
)


def _document(text: str) -> RawEvidenceDocument:
    return RawEvidenceDocument(
        event_id=7,
        raw_version_id=11,
        content_hash=sha256(text.encode()).hexdigest(),
        source_name="news",
        source_document_id="provider-7",
        source_url="https://reuters.com/story/7",
        source_sequence="2026-07-24T14:00:00Z:7:AAPL",
        ticker="AAPL",
        normalized_text=text,
    )


@pytest.mark.parametrize("length", [1, DIRECT_DOCUMENT_CHARS])
def test_short_document_uses_one_exact_raw_span(length: int) -> None:
    # Given
    document = _document("가" * length)

    # When
    spans = build_evidence_spans(document)

    # Then
    assert [(span.start_offset, span.end_offset, span.text) for span in spans] == [
        (0, length, document.normalized_text)
    ]
    assert spans[0].quote_hash == sha256(document.normalized_text.encode()).hexdigest()


def test_long_document_keeps_bounded_resolvable_raw_spans() -> None:
    # Given
    document = _document("A" * 7000 + "B" * 5001)

    # When
    spans = build_evidence_spans(document)

    # Then
    assert sum(len(span.text) for span in spans) == DIRECT_DOCUMENT_CHARS
    assert len(spans) == 2
    assert all(
        document.normalized_text[span.start_offset : span.end_offset] == span.text for span in spans
    )


@pytest.mark.parametrize("text", ["", " " * 20, "x" * (MAX_DOCUMENT_CHARS + 1)])
def test_empty_or_oversized_document_fails_closed(text: str) -> None:
    # Given
    document = _document(text)

    # When / Then
    with pytest.raises(EvidenceDocumentError):
        _ = build_evidence_spans(document)


def test_strategy_input_contains_provenance_raw_spans_and_optional_summary() -> None:
    # Given
    document = _document("material guidance raised")
    spans = build_evidence_spans(document)

    # When
    rendered = render_strategy_evidence(document, spans, "structured summary")

    # Then
    assert document.content_hash in rendered
    assert document.source_sequence in rendered
    assert "material guidance raised" in rendered
    assert "structured summary" in rendered
    assert "[0:24]" in rendered
