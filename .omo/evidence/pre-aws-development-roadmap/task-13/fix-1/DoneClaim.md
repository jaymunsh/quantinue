# DoneClaim — Todo 13 independent-review repair

## Claim

The high-severity provenance gaps in `fe0e282` are repaired across the canonical
schema, atomic migration, executable catalog/behavior expectations, and
integrated-design HTML mirror.

## Closed findings

- `tb_event_raw_document` and `tb_event_raw_version` reject UPDATE/DELETE.
- Normalized events reject blank sources and sources that differ from the
  underlying raw document.
- Evidence insertion deterministically verifies both the event's raw version and
  `end_offset <= normalized_length`.
- Normalized event, evidence, and summary provenance reject UPDATE/DELETE.
- Cursor and processing receipt remain intentionally mutable state machines.
- The event-ledger migration is transaction-scoped, validates required columns,
  fails loudly on incompatible same-name partial state, rolls back partial work,
  and converges after repair/reapply.
- Fresh and upgraded catalogs match structurally, including functions/triggers.

## Evidence

- PIN: `12 passed`.
- RED: `5 failed` for the review findings.
- GREEN: `21 passed`.
- Migration twice: pass.
- Fresh/upgraded catalog diff: zero.
- Incompatible partial migration: non-zero with atomic rollback; recovery: seven
  event tables.
- Manual rejection/read-back matrix: pass.
- Cleanup: task containers absent and port 5490 free.

See `verification.md` and `manual-qa.md` in this directory.
