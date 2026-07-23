# Task 17 Fix 4 Done Claim

Status: PASS

## Contract completed

- Public `build_job_runner` production seam reaches event ingestion, dispatch, analysis,
  the budget guard, and the transport exactly once for strategist and critic.
- Hostile source text remains bounded `ModelInput.external_data`; model input is parsed
  before event, cooldown, or budget ownership changes.
- Event receipts, shared cooldown, and budget reservations distinguish pre-dispatch
  claims from irreversible dispatch. Only pre-dispatch work is releasable/reclaimable.
- Provider failures after dispatch settle the durable reservation at its conservative
  maximum instead of reopening the all-day budget.
- Intraday cooldown completion is decided per ticker from durable analysis outcomes.
- Event strategist signals and critic verdicts persist source, source reference,
  evidence identity, and parent lineage.
- Idle ticks and a reconstructed runner make no additional paid calls.

## Verification

- `pytest` targeted unit + integration suite: `81 passed`
- public production-seam module: `3 passed`
- migration replay against PostgreSQL 16 with `ON_ERROR_STOP=1`: PASS
- Ruff on all task-owned Python files: PASS
- `git diff --check`: PASS
- production-seam BasedPyright: `12 errors, 2 warnings`, identical to the recorded
  pre-Fix-4 baseline (delta: 0)
- protected dirty files retained byte-for-byte:
  - `src/quantinue/main.py`: `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
  - `tests/unit/test_runtime_ownership.py`: `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`

## Runtime hygiene

- Task-owned PostgreSQL container `qn-task17-fix4` was removed after verification.
- Protected services on ports 8020 and 5445 were not touched.
