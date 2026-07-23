from .test_event_storage_contract import event_database, run_migration, run_psql

__all__ = ["event_database"]


def _event_catalog_fingerprint(event_database: str) -> str:
    result = run_psql(
        event_database,
        """
        WITH event_tables(table_name) AS (
          VALUES
            ('tb_event_source_cursor'), ('tb_event_raw_document'),
            ('tb_event_raw_version'), ('tb_normalized_event'),
            ('tb_event_evidence_pack'), ('tb_event_summary_cache'),
            ('tb_event_processing_receipt')
        ),
        catalog AS (
          SELECT 'column|' || c.table_name || '|' || c.ordinal_position || '|' ||
                 c.column_name || '|' || c.data_type || '|' || c.is_nullable ||
                 '|' || coalesce(c.column_default, '') AS entry
          FROM information_schema.columns AS c
          JOIN event_tables USING (table_name)
          WHERE c.table_schema = 'public'
          UNION ALL
          SELECT 'constraint|' || t.relname || '|' || p.conname || '|' ||
                 p.contype::text || '|' || pg_get_constraintdef(p.oid)
          FROM pg_constraint AS p
          JOIN pg_class AS t ON t.oid = p.conrelid
          JOIN pg_namespace AS n ON n.oid = t.relnamespace
          JOIN event_tables ON event_tables.table_name = t.relname
          WHERE n.nspname = 'public'
          UNION ALL
          SELECT 'trigger|' || t.relname || '|' || g.tgname || '|' ||
                 pg_get_triggerdef(g.oid)
          FROM pg_trigger AS g
          JOIN pg_class AS t ON t.oid = g.tgrelid
          JOIN pg_namespace AS n ON n.oid = t.relnamespace
          JOIN event_tables ON event_tables.table_name = t.relname
          WHERE n.nspname = 'public' AND NOT g.tgisinternal
        )
        SELECT string_agg(entry, E'\n' ORDER BY entry) FROM catalog;
        """,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


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


def test_migration_rejects_partial_table_with_guard_columns_but_missing_contract(
    event_database: str,
) -> None:
    # Given: these were the only raw-document columns inspected by the old guard.
    canonical_catalog = _event_catalog_fingerprint(event_database)
    _ = run_psql(
        event_database,
        """
        DROP TABLE tb_event_processing_receipt;
        DROP TABLE tb_event_summary_cache;
        DROP TABLE tb_event_evidence_pack;
        DROP TABLE tb_normalized_event;
        DROP TABLE tb_event_raw_version;
        DROP TABLE tb_event_raw_document;
        CREATE TABLE tb_event_raw_document (
          document_id BIGINT PRIMARY KEY,
          source_name TEXT NOT NULL,
          source_document_id TEXT NOT NULL
        );
        """,
    )

    # When
    rejected = run_migration(event_database, check=False)

    # Then
    assert rejected.returncode != 0
    rolled_back = run_psql(
        event_database,
        "SELECT to_regclass('public.tb_event_raw_version') IS NULL",
    )
    assert rolled_back.stdout.strip() == "t"

    # Given: an operator removes the incompatible partial table.
    _ = run_psql(event_database, "DROP TABLE tb_event_raw_document")

    # When / Then
    _ = run_migration(event_database)
    _ = run_migration(event_database)
    assert _event_catalog_fingerprint(event_database) == canonical_catalog


def test_migration_rejects_preexisting_incoherent_provenance(
    event_database: str,
) -> None:
    # Given: emulate rows accepted before cross-row validation existed.
    _ = run_psql(
        event_database,
        """
        DROP TRIGGER trg_normalized_event_source ON tb_normalized_event;
        DROP TRIGGER trg_event_evidence_span ON tb_event_evidence_pack;
        DROP TRIGGER trg_normalized_event_immutable ON tb_normalized_event;
        DROP TRIGGER trg_event_evidence_immutable ON tb_event_evidence_pack;
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES
          (1, 'wire', 'doc-1', 'https://example.invalid/1', now()),
          (2, 'wire', 'doc-2', 'https://example.invalid/2', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES
          (1, 1, 1, 'hash-1', 'raw', 'short', 5),
          (2, 2, 1, 'hash-2', 'raw', 'other', 5);
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'contradictory', '0001',
                'headline', now(), '{}');
        INSERT INTO tb_event_evidence_pack
          (evidence_id, event_id, raw_version_id,
           start_offset, end_offset, quote_hash)
        VALUES
          (1, 1, 2, 0, 4, 'wrong-version'),
          (2, 1, 1, 0, 6, 'past-end');
        """,
    )

    # When
    rejected = run_migration(event_database, check=False)

    # Then: migration must roll back before it freezes invalid history.
    assert rejected.returncode != 0
    triggers = run_psql(
        event_database,
        """
        SELECT count(*) FROM pg_trigger
        WHERE NOT tgisinternal
          AND tgname IN (
            'trg_normalized_event_source',
            'trg_event_evidence_span',
            'trg_normalized_event_immutable',
            'trg_event_evidence_immutable'
          );
        """,
    )
    assert triggers.stdout.strip() == "0"

    # Given: an operator repairs every rejected lineage contradiction.
    _ = run_psql(
        event_database,
        """
        UPDATE tb_normalized_event SET source_name='wire' WHERE event_id=1;
        UPDATE tb_event_evidence_pack
        SET raw_version_id=1, end_offset=4 WHERE evidence_id=1;
        UPDATE tb_event_evidence_pack SET end_offset=5 WHERE evidence_id=2;
        """,
    )

    # When / Then
    _ = run_migration(event_database)
    _ = run_migration(event_database)
    frozen = run_psql(
        event_database,
        "UPDATE tb_normalized_event SET event_type='changed' WHERE event_id=1",
        check=False,
    )
    assert frozen.returncode != 0
