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


def test_migration_atomically_rejects_same_named_weakened_catalog(
    event_database: str,
) -> None:
    # Given: every object keeps its canonical name while its behavior is weakened.
    _ = run_psql(
        event_database,
        """
        DROP TRIGGER trg_event_evidence_immutable ON tb_event_evidence_pack;
        DROP TRIGGER trg_event_evidence_span ON tb_event_evidence_pack;
        DROP TRIGGER trg_normalized_event_source ON tb_normalized_event;
        ALTER TABLE tb_event_evidence_pack
          DROP CONSTRAINT tb_event_evidence_pack_offsets_check;
        ALTER TABLE tb_event_evidence_pack
          ADD CONSTRAINT tb_event_evidence_pack_offsets_check
          CHECK (end_offset > start_offset);
        ALTER TABLE tb_event_raw_version
          DROP CONSTRAINT tb_event_raw_version_document_id_fkey;
        ALTER TABLE tb_event_raw_version
          ADD CONSTRAINT tb_event_raw_version_document_id_fkey
          FOREIGN KEY (document_id) REFERENCES tb_event_raw_document(document_id)
          ON DELETE CASCADE;
        CREATE SEQUENCE weakened_event_id_seq;
        ALTER TABLE tb_normalized_event
          ALTER COLUMN event_id SET DEFAULT nextval('weakened_event_id_seq');
        CREATE INDEX ix_event_unexpected ON tb_normalized_event (event_type);
        CREATE OR REPLACE FUNCTION enforce_event_evidence_span()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_event_evidence_span
        BEFORE INSERT OR UPDATE ON tb_event_evidence_pack
        FOR EACH ROW EXECUTE FUNCTION enforce_event_evidence_span();
        CREATE TRIGGER trg_normalized_event_source
        BEFORE INSERT ON tb_normalized_event
        FOR EACH STATEMENT EXECUTE FUNCTION enforce_normalized_event_source();
        """,
    )
    exploit = run_psql(
        event_database,
        """
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES (1, 'wire', 'negative-span', 'https://example.invalid/n', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (1, 1, 1, 'negative-span', 'raw', 'short', 5);
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'negative-span', 'wire', '0001', 'headline', now(), '{}');
        INSERT INTO tb_event_evidence_pack
          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
        VALUES (1, 1, -5, -1, 'accepted-by-weakened-check');
        """,
    )
    assert exploit.returncode == 0

    # When
    rejected = run_migration(event_database, check=False)

    # Then: rejection is atomic; migration must not silently replace bad objects.
    assert rejected.returncode != 0
    assert "incompatible event" in rejected.stderr
    trigger = run_psql(
        event_database,
        """
        SELECT lower(pg_get_triggerdef(oid))
        FROM pg_trigger
        WHERE tgname='trg_event_evidence_span';
        """,
    )
    assert "before insert or update" in trigger.stdout

    # Given: the operator removes bad catalog objects before immutable triggers return.
    _ = run_psql(
        event_database,
        """
        DELETE FROM tb_event_evidence_pack
        WHERE quote_hash='accepted-by-weakened-check';
        DROP TRIGGER trg_event_evidence_span ON tb_event_evidence_pack;
        DROP TRIGGER trg_normalized_event_source ON tb_normalized_event;
        DROP FUNCTION enforce_event_evidence_span();
        DROP INDEX ix_event_unexpected;
        ALTER TABLE tb_event_evidence_pack
          DROP CONSTRAINT tb_event_evidence_pack_offsets_check;
        ALTER TABLE tb_event_evidence_pack
          ADD CONSTRAINT tb_event_evidence_pack_offsets_check
          CHECK (start_offset >= 0 AND end_offset > start_offset);
        ALTER TABLE tb_event_raw_version
          DROP CONSTRAINT tb_event_raw_version_document_id_fkey;
        ALTER TABLE tb_event_raw_version
          ADD CONSTRAINT tb_event_raw_version_document_id_fkey
          FOREIGN KEY (document_id) REFERENCES tb_event_raw_document(document_id);
        ALTER TABLE tb_normalized_event ALTER COLUMN event_id
          SET DEFAULT nextval('tb_normalized_event_event_id_seq');
        DROP SEQUENCE weakened_event_id_seq;
        """,
    )

    # When
    _ = run_migration(event_database)
    _ = run_migration(event_database)

    # Then
    negative = run_psql(
        event_database,
        """
        INSERT INTO tb_event_evidence_pack
          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
        VALUES (1, 1, -5, -1, 'must-reject');
        """,
        check=False,
    )
    assert negative.returncode != 0


def test_original_event_catalog_upgrades_and_converges(event_database: str) -> None:
    # Given: the event objects match the original Todo 13 release.
    _ = run_psql(
        event_database,
        """
        DROP TRIGGER trg_normalized_event_source ON tb_normalized_event;
        DROP TRIGGER trg_event_evidence_span ON tb_event_evidence_pack;
        DROP TRIGGER trg_event_raw_document_immutable ON tb_event_raw_document;
        DROP TRIGGER trg_event_raw_version_immutable ON tb_event_raw_version;
        DROP TRIGGER trg_normalized_event_immutable ON tb_normalized_event;
        DROP TRIGGER trg_event_evidence_immutable ON tb_event_evidence_pack;
        DROP TRIGGER trg_event_summary_immutable ON tb_event_summary_cache;
        DROP FUNCTION enforce_normalized_event_source();
        DROP FUNCTION enforce_event_evidence_span();
        DROP FUNCTION reject_event_provenance_mutation();
        ALTER TABLE tb_normalized_event
          DROP CONSTRAINT tb_normalized_event_source_name_check;
        CREATE FUNCTION reject_event_raw_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'tb_event_raw_version is immutable';
        END;
        $$;
        CREATE TRIGGER trg_event_raw_version_immutable
        BEFORE UPDATE OR DELETE ON tb_event_raw_version
        FOR EACH ROW EXECUTE FUNCTION reject_event_raw_version_mutation();
        """,
    )

    # When
    first = run_migration(event_database, check=False)
    second = run_migration(event_database, check=False)

    # Then
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    source_check = run_psql(
        event_database,
        """
        SELECT count(*) FROM pg_constraint
        WHERE conrelid='tb_normalized_event'::regclass
          AND conname='tb_normalized_event_source_name_check'
          AND convalidated;
        """,
    )
    assert source_check.stdout.strip() == "1"


def test_legacy_immutable_triggers_have_explicit_operator_repair_path(
    event_database: str,
) -> None:
    # Given: invalid legacy rows exist and the prior migration restored immutability.
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
          (1, 'wire', 'legacy-1', 'https://example.invalid/1', now()),
          (2, 'wire', 'legacy-2', 'https://example.invalid/2', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES
          (1, 1, 1, 'legacy-1', 'raw', 'short', 5),
          (2, 2, 1, 'legacy-2', 'raw', 'other', 5);
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'legacy-event', 'wrong', '0001', 'headline', now(), '{}');
        INSERT INTO tb_event_evidence_pack
          (evidence_id, event_id, raw_version_id,
           start_offset, end_offset, quote_hash)
        VALUES (1, 1, 2, 0, 4, 'wrong-version');
        CREATE TRIGGER trg_normalized_event_source
        BEFORE INSERT ON tb_normalized_event
        FOR EACH ROW EXECUTE FUNCTION enforce_normalized_event_source();
        CREATE TRIGGER trg_event_evidence_span
        BEFORE INSERT ON tb_event_evidence_pack
        FOR EACH ROW EXECUTE FUNCTION enforce_event_evidence_span();
        CREATE TRIGGER trg_normalized_event_immutable
        BEFORE UPDATE OR DELETE ON tb_normalized_event
        FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
        CREATE TRIGGER trg_event_evidence_immutable
        BEFORE UPDATE OR DELETE ON tb_event_evidence_pack
        FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
        """,
    )

    # When
    rejected = run_migration(event_database, check=False)

    # Then
    assert rejected.returncode != 0
    blocked = run_psql(
        event_database,
        "UPDATE tb_normalized_event SET source_name='wire' WHERE event_id=1",
        check=False,
    )
    assert blocked.returncode != 0

    # Given: the operator drops only the two canonical repair-blocking triggers.
    _ = run_psql(
        event_database,
        """
        DROP TRIGGER trg_normalized_event_immutable ON tb_normalized_event;
        DROP TRIGGER trg_event_evidence_immutable ON tb_event_evidence_pack;
        UPDATE tb_normalized_event SET source_name='wire' WHERE event_id=1;
        UPDATE tb_event_evidence_pack SET raw_version_id=1 WHERE evidence_id=1;
        """,
    )

    # When
    _ = run_migration(event_database)
    _ = run_migration(event_database)

    # Then
    frozen = run_psql(
        event_database,
        "UPDATE tb_normalized_event SET event_type='changed' WHERE event_id=1",
        check=False,
    )
    assert frozen.returncode != 0
