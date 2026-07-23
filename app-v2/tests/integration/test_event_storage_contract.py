"""Behavioral PostgreSQL contracts for the immutable intraday event ledger."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

SCHEMA = Path("db/schema.sql").resolve()


def _docker(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("docker")
    if executable is None:
        pytest.fail("Docker is required for event-storage integration tests")
    return subprocess.run(  # noqa: S603 - fixed executable and argument vector
        [executable, *arguments],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def event_database() -> Iterator[str]:
    name = f"quantinue-events-{uuid4().hex}"
    _ = _docker(
        [
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=test-only",
            "-e",
            "POSTGRES_DB=contracts",
            "-v",
            f"{SCHEMA}:/docker-entrypoint-initdb.d/001.sql:ro",
            "postgres:16-alpine",
        ]
    )
    try:
        for _attempt in range(60):
            owner = _docker(["exec", name, "cat", "/proc/1/comm"], check=False)
            ready = _docker(
                [
                    "exec",
                    name,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "contracts",
                    "-Atc",
                    "SELECT to_regclass('public.tb_event_raw_version') IS NOT NULL",
                ],
                check=False,
            )
            if (
                owner.returncode == 0
                and owner.stdout.strip() == "postgres"
                and ready.returncode == 0
                and ready.stdout.strip() == "t"
            ):
                break
            time.sleep(0.05)
        else:
            pytest.fail("PostgreSQL did not become ready")
        yield name
    finally:
        _ = _docker(["rm", "-f", name], check=False)


def _psql(name: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _docker(
        [
            "exec",
            name,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "contracts",
            "-At",
            "-c",
            sql,
        ],
        check=check,
    )


def _seed_short_document(name: str) -> None:
    _ = _psql(
        name,
        """
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES (1, 'wire', 'doc-1', 'https://example.invalid/1', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (1, 1, 1, 'hash-v1', 'untrusted instruction', 'short', 5);
        """,
    )


def test_raw_versions_preserve_prior_hash_when_source_is_corrected(
    event_database: str,
) -> None:
    # Given
    _seed_short_document(event_database)

    # When
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (2, 1, 2, 'hash-v2', 'corrected data', 'corrected', 9);
        """,
    )

    # Then
    rows = _psql(
        event_database,
        "SELECT version_no || ':' || content_hash FROM tb_event_raw_version ORDER BY version_no",
    )
    assert rows.stdout.splitlines() == ["1:hash-v1", "2:hash-v2"]


def test_raw_version_hash_cannot_be_overwritten(event_database: str) -> None:
    # Given
    _seed_short_document(event_database)
    # When
    changed = _psql(
        event_database,
        "UPDATE tb_event_raw_version SET content_hash='overwritten' WHERE raw_version_id=1",
        check=False,
    )

    # Then
    assert changed.returncode != 0
    assert "immutable" in changed.stderr.lower()


def test_short_document_cannot_have_summary(event_database: str) -> None:
    # Given
    _seed_short_document(event_database)
    # When
    inserted = _psql(
        event_database,
        """
        INSERT INTO tb_event_summary_cache
          (raw_version_id, content_hash, normalized_length, model, prompt_version, summary_text)
        VALUES (1, 'hash-v1', 5, 'model-a', 'prompt-v1', 'summary');
        """,
        check=False,
    )

    # Then
    assert inserted.returncode != 0


def test_long_document_has_exactly_one_summary_per_cache_key(
    event_database: str,
) -> None:
    # Given
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_event_raw_document
          (document_id, source_name, source_document_id, source_url, published_at)
        VALUES (2, 'sec', 'doc-long', 'https://example.invalid/long', now());
        INSERT INTO tb_event_raw_version
          (raw_version_id, document_id, version_no, content_hash, raw_text,
           normalized_text, normalized_length)
        VALUES (3, 2, 1, 'hash-long', 'raw', repeat('x', 12001), 12001);
        """,
    )

    # When
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_event_summary_cache
          (raw_version_id, content_hash, normalized_length, model, prompt_version, summary_text)
        VALUES (3, 'hash-long', 12001, 'model-a', 'prompt-v1', 'one summary');
        """,
    )
    duplicate = _psql(
        event_database,
        """
        INSERT INTO tb_event_summary_cache
          (raw_version_id, content_hash, normalized_length, model, prompt_version, summary_text)
        VALUES (3, 'hash-long', 12001, 'model-a', 'prompt-v1', 'duplicate');
        """,
        check=False,
    )

    # Then
    assert duplicate.returncode != 0
    count = _psql(event_database, "SELECT count(*) FROM tb_event_summary_cache")
    assert count.stdout.strip() == "1"


def test_duplicate_event_and_orphan_evidence_are_rejected(event_database: str) -> None:
    # Given
    _seed_short_document(event_database)
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'wire', '0001', 'headline', now(), '{}'::jsonb);
        """,
    )

    # When
    duplicate = _psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 'event-1', 'wire', '0002', 'headline', now(), '{}'::jsonb);
        """,
        check=False,
    )
    orphan = _psql(
        event_database,
        """
        INSERT INTO tb_event_evidence_pack
          (event_id, raw_version_id, start_offset, end_offset, quote_hash)
        VALUES (999, 1, 0, 4, 'quote-hash');
        """,
        check=False,
    )

    # Then
    assert duplicate.returncode != 0
    assert orphan.returncode != 0


def test_processing_receipt_deduplicates_persona_and_keeps_order_lineage(
    event_database: str,
) -> None:
    # Given
    _seed_short_document(event_database)
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_normalized_event
          (event_id, raw_version_id, event_key, source_name, source_sequence,
           event_type, occurred_at, payload)
        VALUES (1, 1, 'event-1', 'wire', '0001', 'headline', now(), '{}'::jsonb);
        """,
    )
    _ = _psql(
        event_database,
        """
        INSERT INTO tb_event_processing_receipt
          (event_id, ticker, persona, status)
        VALUES (1, 'AAPL', 'aggressive', 'processed');
        """,
    )

    # When
    duplicate = _psql(
        event_database,
        """
        INSERT INTO tb_event_processing_receipt
          (event_id, ticker, persona, status)
        VALUES (1, 'AAPL', 'aggressive', 'processed');
        """,
        check=False,
    )
    missing_order = _psql(
        event_database,
        """
        INSERT INTO tb_event_processing_receipt
          (event_id, ticker, persona, status)
        VALUES (1, 'MSFT', 'conservative', 'ordered');
        """,
        check=False,
    )

    # Then
    assert duplicate.returncode != 0
    assert missing_order.returncode != 0
