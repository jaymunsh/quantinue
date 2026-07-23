# Todo 13 independent-review repair verification

## PIN → RED → GREEN

- PIN command:
  `cd app-v2 && uv run pytest tests/integration/test_schema_sql.py tests/integration/test_event_storage_contract.py -q`
- PIN: `12 passed in 11.64s`.
- RED command:
  `uv run pytest tests/integration/test_event_storage_provenance.py -q`
- RED: `5 failed`; PostgreSQL accepted raw-document mutation, blank or
  contradictory event source, wrong-version/out-of-range evidence, and mutation
  of derived provenance.
- GREEN focused command:
  `uv run pytest tests/integration/test_schema_sql.py tests/integration/test_event_storage_contract.py tests/integration/test_event_storage_provenance.py -q`
- GREEN: `21 passed in 25.31s`.

The catalog suite now reads real non-internal `pg_trigger` definitions and asserts
the two cross-row validation triggers plus five append-only triggers.

## Disposable PostgreSQL 5490

Preflight found stale Todo13-only resource:

```text
name=/quantinue-task13-adversarial
created=2026-07-23T12:45:53.650127134Z
labels={}
ports={"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"5490"}]}
```

Per coordinator direction, that explicitly named stale QA container was removed.
No other container was touched. Registered replacement:
`quantinue-task13-fix`, `127.0.0.1:5490`, `postgres:16-alpine`.

Databases:

1. `fresh`: current `schema.sql`.
2. `migrated`: `fe0e282:app-v2/db/schema.sql`, then current `mvp2.sql` twice.
3. `partial`: current schema, event tables removed, incompatible same-name raw
   document injected, migration rejected, corrected, then migration twice.

Observed:

```text
migration_apply_count=2
catalog_diff_exit=0
incompatible_migration_rc=3
atomic_rollback=true
recovered_event_tables=7
```

The catalog comparison covered every public column, constraint, index,
non-internal trigger, and function.

Cleanup:

```text
docker rm -f quantinue-task13-fix
quantinue-task13-fix
lsof -nP -iTCP:5490 -sTCP:LISTEN
(no output)
docker ps ... | rg '^(quantinue-task13-fix|quantinue-task13-adversarial)$'
(no output)
cleanup_complete
```

Ports 5445 and 8020 were untouched.
