# Task 17 Fix 1 Done Claim

## Outcome

Event-triggered strategist and critic calls now use separate durable, billable
stage boundaries. A completed strategist result is cached in PostgreSQL and is
reused after restart; critic refusal or pre-provider cancellation does not
rebill the strategist. Cancellation after provider dispatch remains uncertain
and cannot be reclaimed.

The default-disabled rejudge path does not construct or dispatch event
analysis, and the production job runner exposes the latest stage counters
without requiring legacy event-runtime test doubles to implement the new
telemetry property.

## Verification

- `uv run ruff check .`: passed.
- `uv run pytest -q tests/unit`: 715 passed.
- Focused PostgreSQL integration matrix:
  `tests/integration/test_event_evidence.py`,
  `tests/integration/test_event_routing.py`, and
  `tests/integration/test_schema_sql.py`: 24 passed.
- Schema contract was run twice after applying `db/migrations/mvp2.sql`
  twice to the same PostgreSQL 16 database: 7 passed.
- Five critical stage-fence tests were repeated ten times: 50/50 passed.
- `uv run python -m compileall -q src`: passed.
- PostgreSQL verified `result_payload` is nullable `jsonb`, a completed
  strategist receipt survives restart with a JSON result, a second event is
  suppressed by cooldown, and `tb_order` remains empty.

## Contract Notes

- Receipt personas are stage-specific, for example
  `analysis:aggressive:strategist`.
- Provider dispatch is recorded only at the budgeted analyzer's immediate
  provider boundary.
- Pre-boundary cancellation releases the unbilled stage; post-boundary
  cancellation is durable and uncertain.
- Completion persists the provider result before a later stage can be
  claimed.
- The schema migration is idempotent on both fresh-schema and already-upgraded
  databases.

## Isolation

Validation used task-owned container `qn-task17-fix1` on
`127.0.0.1:5490`. Existing listeners on ports 8020 and 5445 were inspected
read-only and were not modified. The task-owned container is removed during
cleanup.
