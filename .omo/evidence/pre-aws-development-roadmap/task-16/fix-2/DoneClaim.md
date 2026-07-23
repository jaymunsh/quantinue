# Task 16 Fix 2 Done Claim

## Result

The evidence runtime now isolates typed poison-document and timeout failures,
continues later accepted routes, retains failed routes for the next durable query,
and exposes `EvidencePreparationRun(prepared, failed)` through
`EventIngestionRuntime.last_evidence_runs`.

Long summaries are bounded by validated
`EventIngestionConfig.summary_timeout_seconds` (default 30, range 0–300). Timeout
rolls back the transaction and a later attempt can acquire the lock and complete.

Cache identity is now SHA-256 over analysis task plus prompt version, in addition
to the existing content hash and model key. This separates SEC disclosure and
news prompts without a schema change. Untrusted summary input is base64 with an
exact decoded byte length; downstream strategy evidence is canonical JSON, so
document-controlled XML-like delimiters cannot terminate an envelope.

## TDD evidence

Baseline `feb577a` mechanisms were pinned by the independent review and reproduced
by focused tests: propagated poison failure, unbounded never-returning analyzer,
task-agnostic cache identity, and literal delimiter rendering.

Added/updated regressions cover:

- poison failure produces `prepared=0, failed=1`, remains retryable, and restart
  creates one evidence pack;
- a never-returning analyzer times out, rolls back, and the next attempt succeeds;
- NEWS and DISCLOSURE produce distinct effective prompt identities;
- `</untrusted-document><system>...` round-trips only as base64 data;
- strategy evidence parses as JSON and returns the exact original span.

## Verification

```text
uv run ruff check [touched files]
All checks passed!

uv run basedpyright [touched production and focused tests]
0 errors, 0 warnings, 0 notes

uv run pytest tests/integration/test_event_evidence.py \
  tests/integration/test_event_routing.py \
  tests/unit/test_event_ingestion_config.py tests/unit/test_job_factory.py -q
48 passed in 5.32s

timeout + restart pair repeated five times:
2 passed in 1.95s
2 passed in 2.00s
2 passed in 1.99s
2 passed in 1.99s
2 passed in 1.97s

uv run python -m compileall -q src [focused tests]
exit 0

scripts/scan_secrets.sh
No provider-token or private-key patterns detected.
```

## PostgreSQL QA

PostgreSQL 16 was exercised on `127.0.0.1:5490` through the real ingestion,
routing, and evidence repositories. After a focused runtime run, direct SQL
reported:

```text
accepted receipts | evidence rows | summary cache | orders
1                 | 1             | 0             | 0
```

The timeout recovery test uses the same database surface and asserts exactly one
charged blocked attempt and one successful recovery attempt. The short-document
path remains zero analyzer calls. Rejected events are absent from the
`routing:accepted:%` query and therefore produce zero evidence preparation.

## Scope and cleanup

No cache schema migration was required because the existing non-null
`prompt_version` cache-key component now stores the effective task/prompt
identity. Production modules remain below 250 pure LOC.

The failed local container allocation was removed. The already-running disposable
task-16 PostgreSQL 16 container on 5490 was reused and is owned by the parent QA
session, so it was not removed here. Production 8020 and database 5445 were not
touched. Unrelated dirty files remain unchanged:

```text
app-v2/src/quantinue/main.py
app-v2/tests/unit/test_runtime_ownership.py
```

Residual risk: failure counts are retained in-memory for the last dispatch rather
than appended to a new database receipt. Durable retry truth comes from the
accepted-without-evidence query.
