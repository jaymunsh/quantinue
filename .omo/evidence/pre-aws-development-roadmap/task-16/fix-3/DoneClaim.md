# Task 16 Fix 3 Done Claim

## Outcome

The cumulative Todo 16 contract is green. Canonical JSON rendering now has an
exact unit assertion, production factory assembly exposes and verifies the
evidence repository plus selected analyzer, poison evidence is isolated while a
later route completes in the same pass, and a fresh runtime recovers the failed
route.

Runtime lifecycle cleanup is shielded at JobRunner, EventIngestionRuntime, and
EventIngestionExecutor boundaries. An awaiting disposal fake proves active
cancellation cannot skip completion. Tick observability is one combined
`EvidencePreparationRun` whose prepared/failed totals cover the whole tick,
rather than a duplicate-prone per-source tuple.

## Red and regression evidence

- Baseline cumulative unit failure:
  `tests/unit/test_event_evidence.py:84` expected legacy `[0:24]`.
- Replacement asserts the full canonical JSON value, provenance, summary, and
  exact span round-trip.
- Factory regression asserts `PostgresEventEvidenceRepository` and the exact
  selected `DeterministicAnalyzer` are present in the production runtime.
- PostgreSQL poison/valid test observes `prepared=1, failed=1` in one pass and
  then two accepted receipts/two evidence rows after a fresh runtime.
- Awaiting close test cancels while disposal is blocked and proves disposal still
  finishes.

## Verification

```text
Cumulative Todo16 suite:
59 passed in 5.48s

Retry + timeout + cancellation loop, ten repetitions:
3 passed per repetition (10/10)

Ruff:
All checks passed!

Focused basedpyright:
0 errors, 0 warnings, 0 notes

compileall:
exit 0

secret scan:
No provider-token or private-key patterns detected.
```

`job_runner.py` and the full legacy `test_job_factory.py` retain pre-existing
strict basedpyright errors outside this change; their exercised runtime tests and
Ruff checks pass.

## Manual PostgreSQL evidence

PostgreSQL 16 ran on `127.0.0.1:5490` using the real schema and repository path.
After the timeout/recovery scenario, direct SQL returned:

```text
accepted receipts | evidence spans | summary cache | orders
1                 | 2              | 1             | 0
```

The same-pass poison test separately asserts two accepted receipts and two
evidence rows after fresh-runtime recovery, with zero short-document analyzer
calls.

## Cleanup and scope

The disposable `quantinue-task16-fix3` container was removed and 5490/8021 were
verified free. Production 8020 and database 5445 identities were not touched.
Protected dirty files retained their original hashes:

```text
app-v2/src/quantinue/main.py
app-v2/tests/unit/test_runtime_ownership.py
```
