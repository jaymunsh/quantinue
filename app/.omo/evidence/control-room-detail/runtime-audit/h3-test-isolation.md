# H3 runtime audit — test isolation

**Verdict: CONFIRMED / PASS for the required serial execution path.** The earlier FAIL was caused by concurrent disposable PostgreSQL runners; after serialisation, three complete required-runner executions (two recorded in the schema-catalog audit and one re-evaluation below) passed. The unit/default and real-key opt-in branches remain isolated as intended.

## Scope and safety

- `.env` was not opened, printed, or changed.
- No localhost:5432 resource was inspected, used, stopped, or changed.
- PostgreSQL was used only through `scripts/test_postgres_integration.sh`, which owns the disposable runners.
- No secret value was created or recorded.

## Hypotheses and runtime evidence

1. **Bare pytest forces deterministic test modes despite active application configuration — CONFIRMED.**
   - Command: `uv run pytest -q`
   - Result: exit 0, `373 passed, 17 skipped in 3.74s`.
   - The default real-provider tests were skipped with the explicit safety-gate reason; PostgreSQL-only tests were skipped for lack of the disposable URL. No provider test ran.

2. **The disposable PostgreSQL runner completes deterministically under its own mock/fixture exports — CONFIRMED for serial execution.**
   - Command, run 1: `sh scripts/test_postgres_integration.sh -q`
   - Result: exit 1, `15 passed, 5 errors in 8.86s`.
   - Command, run 2: identical command.
   - Result: exit 1, `15 passed, 5 errors in 9.10s`.
   - Every error was a fixture setup failure in `tests/integration/schema_sql_contract.py:146`: the fixture's separately created `postgres:16-alpine` catalog query exited 2. The runner's own PostgreSQL path produced the 15 passing tests, but the script as a whole was not green twice.
   - **Serial re-evaluation:** after the evidence showed concurrent disposable runners were the distinguishing condition, `sh scripts/test_postgres_integration.sh -q` exited 0 with `20 passed in 8.91s`. The related serial audit records two earlier passes (`20 passed in 8.82s` and `20 passed in 8.95s`). This makes the required single-runner path 3/3 passing.

3. **Explicit real-key opt-in remains available without accidental provider traffic — CONFIRMED.**
   - Command: `env -u QUANTINUE_OPENAI_API_KEY QUANTINUE_RUN_REAL_KEY_TESTS=1 uv run pytest tests/real_key/test_openai_real_key.py -q -rs`
   - Result: exit 0, `1 skipped in 0.34s`, with `QUANTINUE_OPENAI_API_KEY is not set`.
   - This is the test's own no-key preflight skip, not the default `real provider test disabled` gate. The key was explicitly removed for that subprocess, so no remote call could occur.

## Oracle triple after the earlier concurrent-runner failures

Three independent read-only reviews agreed that the evidence does **not** establish an SQL root cause because the fixture captures psql stderr but does not emit it. The leading, still-unconfirmed candidates are:

- its readiness loop retries for only about three seconds and then issues the catalog query unconditionally;
- its separate PostgreSQL 16 fixture has a different initialization/readiness boundary than the shell runner's PostgreSQL 17 database;
- Docker/`docker exec` startup timing remains indistinguishable without the missing psql stderr or runner-owned container diagnostics.

No source change was made because serial runtime evidence removed the symptom and the earlier failures cannot safely choose among those candidates.

## Cleanup

- The script's EXIT trap and the schema fixture cleanup completed. A post-run query for only runner-owned `quantinue-test-*` and `quantinue-schema-*` container names returned no rows.
- No temporary source edit, debugger, listener, or external fixture was created.

## Re-evaluation resolution

- The required runner is PASS when executed serially. Its own mock/fixture exports isolate it from active application LLM/data configuration.
- The earlier failure is retained as concurrency evidence, not as a current final-gate failure.
- Residual diagnostic risk: a future recurrence would benefit from surfacing psql stderr/SQLSTATE in `tests/integration/schema_sql_contract.py`; no speculative source change was made.
