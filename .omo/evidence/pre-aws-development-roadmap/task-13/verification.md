# Task 13 verification

## PIN → RED → GREEN

- PIN: pre-change `tests/integration/test_schema_sql.py` catalog suite passed and the
  canonical HTML schema section contained the existing raw/watch mirrors.
- RED command:
  `cd app-v2 && uv run pytest tests/integration/test_schema_sql.py tests/integration/test_event_storage_contract.py -q`
- RED result: `7 failed, 5 passed`; missing event tables and constraints were the
  failure reason.
- GREEN command (repeated to expose flakes):
  `cd app-v2 && uv run pytest tests/integration/test_schema_sql.py tests/integration/test_event_storage_contract.py -q`
- GREEN results: `12 passed in 11.44s`; `12 passed in 11.88s`.
- The repeat exposed an initdb temporary-postmaster readiness race in the existing
  catalog fixture. The fixture now waits for PID 1 `postgres`, not merely a
  transient complete table list.

## Automated gates

- `uv run ruff check tests/integration/schema_sql_expectations.py tests/integration/test_event_storage_contract.py`
  → `All checks passed!`
- `uv run basedpyright tests/integration/schema_sql_expectations.py tests/integration/test_event_storage_contract.py`
  → `0 errors, 0 warnings, 0 notes`
- `uv run python -m compileall -q tests/integration/schema_sql_expectations.py tests/integration/test_event_storage_contract.py`
  → exit 0.
- `git diff --check` → exit 0.

## Disposable PostgreSQL 5490

Registered resource before creation:
`quantinue-task13-postgres`, host port `127.0.0.1:5490`, image
`postgres:16-alpine`. Preflight `lsof` and container search returned no owner.

Applied:

1. current `app-v2/db/schema.sql` to database `fresh`;
2. committed pre-task schema (`git show HEAD:app-v2/db/schema.sql`) to `migrated`;
3. current `app-v2/db/migrations/mvp2.sql` to `migrated` twice.

Observed: `MIGRATION_APPLY_COUNT=2`; all seven logical event tables existed
(`tb_normalized_event` plus six `tb_event_*` tables). A structural catalog query
over every public column, constraint, index, trigger, and function returned
`CATALOG_DIFF_EXIT=0` for `fresh` versus `migrated`.

Interrupted/resumed simulation applied the migration through immutable raw-version
creation, then reapplied the complete migration. Observed
`resumed_event_tables=7` and `raw_trigger_count=2` (information_schema emits one
row for each UPDATE/DELETE trigger event).

Cleanup:

```text
docker rm -f quantinue-task13-postgres
quantinue-task13-postgres
lsof -nP -iTCP:5490 -sTCP:LISTEN
(no output)
docker ps -a ... | rg '^quantinue-task13-postgres$'
(no output)
cleanup_complete
```

No command addressed app port 8020 or PostgreSQL port 5445.
