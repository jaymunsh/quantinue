# Resilience repair evidence

## Regression covered

- `test_postgres_failed_run_resumes_from_checkpoint_not_terminal_payload` creates a
  real PostgreSQL run where stage `01` checkpoints its `PipelineContext`, stage
  `02` times out, and `finish_run` replaces `pipeline_runs.payload` with a
  terminal `PipelineRun`. The retry claim must restore the latest checkpoint,
  retain `last_price`, skip stage `01`, and finish stage `02`.
- `test_postgres_atomic_claim_and_process_recreation_resume` is the companion
  interruption case: a prior owner leaves `02/1` running, the next claimant
  records it as `failed` with `ABANDONED_ATTEMPT`, and completes `02/2`.

## Commands and results

```text
sh scripts/test_postgres_integration.sh -q -k \
  'postgres_atomic_claim_and_process_recreation_resume or \
   postgres_failed_run_resumes_from_checkpoint_not_terminal_payload'
2 passed, 14 deselected in 2.96s

uv run pytest -q tests/unit/test_persistence_orchestration.py \
  tests/unit/test_pipeline_resilience.py tests/unit/test_retry.py \
  tests/integration/test_postgres_resume.py
32 passed, 1 skipped in 0.34s

uv run ruff format --check <touched files>
5 files already formatted
uv run ruff check <touched files>
All checks passed!
uv run basedpyright <touched files>
0 errors, 0 warnings, 0 notes

sh scripts/test_postgres_integration.sh -q
exit 0
```

## Isolation and cleanup

`scripts/test_postgres_integration.sh` selects a free loopback port in
`55400-55499`, starts one uniquely named `quantinue-test-pg-*` PostgreSQL
container, and removes it through its shell `trap` on every exit. It never
targets or changes localhost port `5432` or the product host port `5444`.
