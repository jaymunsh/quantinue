# Task 16 Fix 4 Done Claim

## Outcome

Evidence preparation is now a two-phase tick: all due sources ingest and route,
then the global accepted-without-evidence backlog is prepared exactly once.
The three default due sources therefore attempt one retained poison route once,
not three times. The PostgreSQL poison/valid regression observes one failed and
one prepared route in the same pass, followed by successful fresh-runtime retry.

Budget exhaustion, usage-bound exhaustion, typed evidence failures, and summary
timeouts are isolated per route and remain retryable. Structured summaries are
fail-closed above `MAX_SUMMARY_CHARS = 4_000`; no truncated evidence is stored.
The oversized-summary regression also exposed and fixed frozen exception
traceback mutation during transaction rollback.

Cleanup remains shielded across JobRunner, runtime, and all three repository
owners. The awaiting cancellation regression proves completion.

## Verification

Exact cumulative command:

```text
uv run pytest tests/unit/test_event_evidence.py
  tests/unit/test_event_ingestion_config.py
  tests/unit/test_event_ingestion_runtime.py
  tests/unit/test_job_factory.py
  tests/integration/test_event_evidence.py
  tests/integration/test_event_routing.py -q

60 passed in 5.84s
```

Multi-source retry, timeout recovery, and cancellation cleanup were repeated ten
times; every repetition reported `3 passed`.

```text
focused basedpyright: 0 errors, 0 warnings, 0 notes
Ruff: all checks passed
compileall: exit 0
secret scan: no provider-token or private-key patterns
```

## PostgreSQL and cleanup

Real PostgreSQL 16 ran at `127.0.0.1:5490` with `db/schema.sql`. Repository tests
used direct routing receipts, evidence spans, summary cache rows, advisory locks,
rollback, restart, and analyzer counters. The disposable
`quantinue-task16-fix4` container was removed; 5490 and 8021 were verified free.
Production 8020 and database 5445 were not touched.

Protected dirty files retained their original hashes:

```text
app-v2/src/quantinue/main.py
app-v2/tests/unit/test_runtime_ownership.py
```
