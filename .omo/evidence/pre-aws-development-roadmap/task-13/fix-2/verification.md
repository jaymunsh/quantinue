# Todo 13 migration hardening verification

## Reproduced RED

Command:

`uv run pytest tests/integration/test_event_storage_provenance.py -k 'guard_columns or incoherent_provenance' -q`

Result before production changes:

`2 failed, 8 deselected`

The first failure showed that a raw-document table containing only the three
columns inspected by the old guard migrated with return code 0. The second
showed that contradictory event source, wrong evidence raw version, and an
out-of-range evidence span migrated with return code 0.

## GREEN

The migration now checks the complete seven-table column catalog, including
type, nullability, and material defaults; the complete named PK, UNIQUE, FK, and
CHECK catalog; and the final trigger set. It audits existing event/evidence
lineage before append-only triggers are installed.

Focused contract result:

`23 passed in 29.18s`

The recovery tests apply the migration twice and compare the recovered catalog
with the catalog captured from a fresh schema.
