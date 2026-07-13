# Schema catalog disposable PostgreSQL debug journal

Started: 2026-07-13
Goal: Determine whether the schema catalog fixture can fail in the required serial disposable PostgreSQL runner, without touching localhost:5432 or product Compose.

## Scope and environment

- Runtime: Python via `uv run pytest`; disposable Docker PostgreSQL only.
- Required repro command: `sh scripts/test_postgres_integration.sh -q`.
- Explicit exclusions: localhost:5432, product Docker Compose, `.env`, credentials, and persistent Docker resources.
- Existing runner: PostgreSQL 17 Alpine, host port selected only from 55400-55499.
- Nested catalog fixture: PostgreSQL 16 Alpine with no published port; `tests/integration/schema_sql_contract.py:79`.

## References read

- `debugging/SKILL.md`
- `references/runtimes/python.md`
- `references/methodology/00-setup.md`
- `references/methodology/02-investigate.md`
- `references/methodology/06-fix.md`
- `references/methodology/08-qa.md`
- `references/methodology/09-cleanup.md`

## Hypotheses

1. [OPEN] The catalog fixture's 3-second polling budget expires before `postgres:16-alpine` finishes init SQL under load. Distinguishing evidence: serial runner reports the catalog tests' `psql` error or a direct fixture trace shows no exact table set before the deadline. If true, fix: bounded readiness.
2. [CONFIRMED FOR REQUIRED SERIAL PATH] A transient Docker/daemon contention caused the observed failure while multiple runners were active, but the serial required runner is stable. Distinguishing evidence: two consecutive bare serial runs pass and no runner-owned containers remain. Fix: no product change.
3. [CONFIRMED OBSERVABILITY GAP, NOT TRIGGERED] The catalog fixture proceeds after an unsuccessful readiness loop and hides the useful PostgreSQL diagnostic, making a real schema/init error opaque. Distinguishing evidence: `tests/integration/schema_sql_contract.py:108-132` exits the polling loop without an assertion before issuing the line-146 catalog `psql` call. Fix: fail loudly only if a failure is reproducible.

## Artifacts and cleanup

- [x] This evidence journal only; it is a requested durable artifact.
- [x] Disposable runner-owned containers from each `scripts/test_postgres_integration.sh` invocation. The script's EXIT trap ran; the bounded name-only check returned no `quantinue-test-pg-` or `quantinue-schema-` containers.

## Findings

- 2026-07-13, serial run 1: `sh scripts/test_postgres_integration.sh -q` exited 0 with `20 passed in 8.82s`.
- 2026-07-13, serial run 2: `sh scripts/test_postgres_integration.sh -q` exited 0 with `20 passed in 8.95s`.
- Both executions used exactly the required disposable runner command; no concurrent PostgreSQL runner was started by this audit.
- The observed H3 symptom (`15 passed, 5 errors`, catalog fixture `psql` exit 2) did not reproduce in either full serial execution.
- The fixture's readiness polling is bounded to 60 x 0.05 seconds and does not assert that `tables == TABLES` after the loop. This is a latent diagnostic weakness, but changing it without a serial repro would be a speculative product change.
- Cleanup verification: `docker ps -a --format '{{.Names}}' --filter 'name=^quantinue-test-pg-' --filter 'name=^quantinue-schema-'` produced no output. This name-scoped check did not inspect unrelated containers.

## Resolution

- Runtime truth for the requested serial path: PASS twice, 20/20 tests each run.
- No source or test modification was warranted: the reported failure was not reproducible after removing concurrent disposable-runner activity, and the final required bare runner is stable in this audit.
- Residual risk: the catalog fixture would give poor detail if its short readiness window ever expires. Treat a future recurrence as the trigger for a minimal readiness assertion/diagnostic change with a failing-first test.
