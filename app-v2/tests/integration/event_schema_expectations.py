"""Expected identities and constraints for the intraday event ledger."""

from typing import TypeAlias

ForeignKey: TypeAlias = tuple[tuple[str, ...], str, tuple[str, ...]]

EVENT_TABLES = {
    "tb_event_source_cursor",
    "tb_event_raw_document",
    "tb_event_raw_version",
    "tb_normalized_event",
    "tb_event_evidence_pack",
    "tb_event_summary_cache",
    "tb_event_processing_receipt",
}
EVENT_PK = {
    "tb_event_source_cursor": ("source_name",),
    "tb_event_raw_document": ("document_id",),
    "tb_event_raw_version": ("raw_version_id",),
    "tb_normalized_event": ("event_id",),
    "tb_event_evidence_pack": ("evidence_id",),
    "tb_event_summary_cache": ("summary_id",),
    "tb_event_processing_receipt": ("receipt_id",),
}
EVENT_UNIQUE = {
    "tb_event_raw_document": {("source_name", "source_document_id")},
    "tb_event_raw_version": {
        ("document_id", "version_no"),
        ("document_id", "content_hash"),
        ("raw_version_id", "content_hash", "normalized_length"),
    },
    "tb_normalized_event": {
        ("event_key",),
        ("source_name", "source_sequence"),
    },
    "tb_event_evidence_pack": {
        ("event_id", "raw_version_id", "start_offset", "end_offset"),
    },
    "tb_event_summary_cache": {("content_hash", "model", "prompt_version")},
    "tb_event_processing_receipt": {("event_id", "ticker", "persona")},
}
EVENT_FK: dict[str, set[ForeignKey]] = {
    "tb_event_raw_version": {
        (("document_id",), "tb_event_raw_document", ("document_id",))
    },
    "tb_normalized_event": {
        (("raw_version_id",), "tb_event_raw_version", ("raw_version_id",))
    },
    "tb_event_evidence_pack": {
        (("event_id",), "tb_normalized_event", ("event_id",)),
        (("raw_version_id",), "tb_event_raw_version", ("raw_version_id",)),
    },
    "tb_event_summary_cache": {
        (
            ("raw_version_id", "content_hash", "normalized_length"),
            "tb_event_raw_version",
            ("raw_version_id", "content_hash", "normalized_length"),
        )
    },
    "tb_event_processing_receipt": {
        (("event_id",), "tb_normalized_event", ("event_id",)),
        (("order_id",), "tb_order", ("id",)),
    },
}
EVENT_CHECKS = {
    "tb_event_source_cursor": {
        ("source_name",): ("length(btrim(source_name)) > 0",),
        ("cursor_value",): ("length(btrim(cursor_value)) > 0",),
    },
    "tb_event_raw_document": {
        ("source_name",): ("length(btrim(source_name)) > 0",),
        ("source_document_id",): ("length(btrim(source_document_id)) > 0",),
    },
    "tb_event_raw_version": {
        ("version_no",): ("version_no > 0",),
        ("content_hash",): ("length(btrim(content_hash)) > 0",),
        ("normalized_length", "normalized_text"): (
            "normalized_length >= 0",
            "normalized_length = char_length(normalized_text)",
        ),
    },
    "tb_normalized_event": {
        ("event_key",): ("length(btrim(event_key)) > 0",),
        ("source_name",): ("length(btrim(source_name)) > 0",),
        ("source_sequence",): ("length(btrim(source_sequence)) > 0",),
        ("event_type",): ("length(btrim(event_type)) > 0",),
    },
    "tb_event_evidence_pack": {
        ("start_offset", "end_offset"): (
            "start_offset >= 0",
            "end_offset > start_offset",
        ),
        ("quote_hash",): ("length(btrim(quote_hash)) > 0",),
    },
    "tb_event_summary_cache": {
        ("normalized_length",): ("normalized_length > 12000",),
        ("content_hash",): ("length(btrim(content_hash)) > 0",),
        ("model",): ("length(btrim(model)) > 0",),
        ("prompt_version",): ("length(btrim(prompt_version)) > 0",),
        ("summary_text",): ("length(btrim(summary_text)) > 0",),
    },
    "tb_event_processing_receipt": {
        ("ticker",): ("length(btrim(ticker)) > 0",),
        ("persona",): ("length(btrim(persona)) > 0",),
        ("status",): ("'claimed'", "'processed'", "'skipped'", "'ordered'"),
        ("status", "order_id"): ("'ordered'", "order_id is not null"),
    },
}

EVENT_TRIGGERS = {
    "trg_normalized_event_source": (
        "before insert",
        "enforce_normalized_event_source()",
    ),
    "trg_event_evidence_span": (
        "before insert",
        "enforce_event_evidence_span()",
    ),
    "trg_event_raw_document_immutable": (
        "before delete or update",
        "reject_event_provenance_mutation()",
    ),
    "trg_event_raw_version_immutable": (
        "before delete or update",
        "reject_event_provenance_mutation()",
    ),
    "trg_normalized_event_immutable": (
        "before delete or update",
        "reject_event_provenance_mutation()",
    ),
    "trg_event_evidence_immutable": (
        "before delete or update",
        "reject_event_provenance_mutation()",
    ),
    "trg_event_summary_immutable": (
        "before delete or update",
        "reject_event_provenance_mutation()",
    ),
}
