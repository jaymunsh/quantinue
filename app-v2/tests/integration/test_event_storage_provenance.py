"""Cross-row provenance and append-only event-ledger contracts."""

from .test_event_storage_contract import (
    event_database,
    run_migration,
    run_psql,
    seed_short_document,
)

__all__ = ["event_database"]


def test_raw_document_is_append_only(event_database: str) -> None:
    # Given
    seed_short_document(event_database)

    # When
    updated = run_psql(
        event_database,
        "UPDATE tb_event_raw_document SET source_url='changed' WHERE document_id=1",
        check=False,
    )
    deleted = run_psql(
        event_database,
        "DELETE FROM tb_event_raw_document WHERE document_id=1",
        check=False,
    )

    # Then
    assert updated.returncode != 0
    assert deleted.returncode != 0


def test_event_source_must_match_its_raw_document(event_database: str) -> None:
    # Given
    seed_short_document(event_database)

    # When
    blank = run_psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 'blank-source', ' ', '0001', 'headline', now(), '{}');
        """,
        check=False,
    )
    contradictory = run_psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 'wrong-source', 'sec', '0001', 'headline', now(), '{}');
        """,
        check=False,
    )

    # Then
    assert blank.returncode != 0
    assert contradictory.returncode != 0


def test_evidence_span_must_belong_to_event_version_and_fit_text(
    event_database: str,
) -> None:
    # Given
    seed_short_document(event_database)
    _ = run_psql(
        event_database,
        """
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES (2, 'wire', 'doc-2', 'https://example.invalid/2', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (2, 2, 1, 'hash-v2', 'other', 'other', 5);
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'wire', '0001', 'headline', now(), '{}');
        """,
    )

    # When
    wrong_version = run_psql(
        event_database,
        """
        INSERT INTO tb_event_evidence_pack
          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
        VALUES (1, 2, 0, 4, 'wrong-version');
        """,
        check=False,
    )
    out_of_range = run_psql(
        event_database,
        """
        INSERT INTO tb_event_evidence_pack
          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
        VALUES (1, 1, 0, 6, 'past-end');
        """,
        check=False,
    )

    # Then
    assert wrong_version.returncode != 0
    assert out_of_range.returncode != 0


def test_derived_provenance_rows_are_append_only(event_database: str) -> None:
    # Given
    seed_short_document(event_database)
    _ = run_psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'wire', '0001', 'headline', now(), '{}');
        INSERT INTO tb_event_evidence_pack
          (evidence_id, event_id, raw_version_id,
           start_offset, end_offset, quote_hash)
        VALUES (1, 1, 1, 0, 5, 'quote-hash');
        """,
    )

    # When
    event_update = run_psql(
        event_database,
        "UPDATE tb_normalized_event SET event_type='changed' WHERE event_id=1",
        check=False,
    )
    evidence_delete = run_psql(
        event_database,
        "DELETE FROM tb_event_evidence_pack WHERE evidence_id=1",
        check=False,
    )

    # Then
    assert event_update.returncode != 0
    assert evidence_delete.returncode != 0


def test_summary_cache_is_append_only(event_database: str) -> None:
    # Given
    _ = run_psql(
        event_database,
        """
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES (1, 'sec', 'long-doc', 'https://example.invalid/long', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (1, 1, 1, 'long-hash', 'raw', repeat('x', 12001), 12001);
        INSERT INTO tb_event_summary_cache
          (summary_id, raw_version_id, content_hash, normalized_length,
           model, prompt_version, summary_text)
        VALUES (1, 1, 'long-hash', 12001, 'model-a', 'prompt-v1', 'summary');
        """,
    )

    # When
    updated = run_psql(
        event_database,
        "UPDATE tb_event_summary_cache SET summary_text='changed' WHERE summary_id=1",
        check=False,
    )

    # Then
    assert updated.returncode != 0


def test_migration_rejects_incompatible_partial_state_then_recovers(
    event_database: str,
) -> None:
    # Given
    _ = run_psql(
        event_database,
        """
        DROP TABLE tb_event_processing_receipt;
        DROP TABLE tb_event_summary_cache;
        DROP TABLE tb_event_evidence_pack;
        DROP TABLE tb_normalized_event;
        DROP TABLE tb_event_raw_version;
        DROP TABLE tb_event_raw_document;
        CREATE TABLE tb_event_raw_document (document_id BIGINT PRIMARY KEY);
        """,
    )

    # When
    rejected = run_migration(event_database, check=False)

    # Then
    assert rejected.returncode != 0
    partial = run_psql(
        event_database,
        "SELECT to_regclass('public.tb_normalized_event') IS NULL",
    )
    assert partial.stdout.strip() == "t"

    # Given
    _ = run_psql(event_database, "DROP TABLE tb_event_raw_document")

    # When
    _ = run_migration(event_database)

    # Then
    recovered = run_psql(
        event_database,
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema='public'
          AND table_name IN (
            'tb_event_source_cursor', 'tb_event_raw_document',
            'tb_event_raw_version', 'tb_normalized_event',
            'tb_event_evidence_pack', 'tb_event_summary_cache',
            'tb_event_processing_receipt'
          );
        """,
    )
    assert recovered.stdout.strip() == "7"


def test_source_cursor_remains_mutable_checkpoint_state(event_database: str) -> None:
    # Given
    _ = run_psql(
        event_database,
        """
        INSERT INTO tb_event_source_cursor
          (source_name, cursor_value, checkpoint_at)
        VALUES ('wire', 'cursor-1', now());
        """,
    )

    # When
    _ = run_psql(
        event_database,
        """
        UPDATE tb_event_source_cursor
        SET cursor_value='cursor-2', checkpoint_at=now(), updated_at=now()
        WHERE source_name='wire';
        """,
    )

    # Then
    cursor = run_psql(
        event_database,
        "SELECT cursor_value FROM tb_event_source_cursor WHERE source_name='wire'",
    )
    assert cursor.stdout.strip() == "cursor-2"


def test_processing_receipt_remains_mutable_state_machine(
    event_database: str,
) -> None:
    # Given
    seed_short_document(event_database)
    _ = run_psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'wire', '0001', 'headline', now(), '{}');
        INSERT INTO tb_event_processing_receipt
          (receipt_id, event_id, ticker, persona, status)
        VALUES (1, 1, 'AAPL', 'aggressive', 'claimed');
        """,
    )

    # When
    _ = run_psql(
        event_database,
        """
        UPDATE tb_event_processing_receipt
        SET status='processed', completed_at=now()
        WHERE receipt_id=1;
        """,
    )

    # Then
    status = run_psql(
        event_database,
        "SELECT status FROM tb_event_processing_receipt WHERE receipt_id=1",
    )
    assert status.stdout.strip() == "processed"
