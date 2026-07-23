# Task 17 Fix 5 Done Claim

Status: PASS

## Fixed contracts

- Cooldown and event dispatch now occur through a typed transport-start boundary
  after budget admission, rather than before the budget reservation.
- Pre-transport budget refusal, cancellation, and ordinary failures release the
  owner-matched event and canonical cooldown claims.
- Durable budget acquisition owns its caller-generated reservation identity before
  awaiting PostgreSQL; acquisition is shielded and stale claimed reservations are
  reclaimed without reopening dispatched work.
- Dispatched provider failures remain fail-closed and settle at maximum usage.
- Event signal and verdict evidence identities are unique and canonical writes reuse
  the existing row on idle or reconstructed-runner replay.
- The cooldown lifecycle is represented by one catalog-auditable CHECK constraint,
  and migration retries drop/recreate its stable name idempotently.
- Critic lineage uses `lineage_source`, preserving the separate `verdict_source`
  contract without reintroducing the ambiguous `source` attribute.

## Verification

- Unit suite: `720 passed`, twice.
- Authoritative unit/PostgreSQL matrix: `109 passed`, twice.
- Public production seam stress: `3 passed` per run, ten runs (`30/30`).
- Final replay SQL: usage `2`, event strategist signals `1`, event critic verdicts
  `1`, and provider call count unchanged.
- Event migration adversarial recovery: `6 passed`.
- Fresh PostgreSQL schema catalog: `7 passed`.
- Migration replay with `ON_ERROR_STOP=1`: passed twice.
- Focused cancellation/budget/event suite: `82 passed`.
- Ruff, Python compileall, `git diff --check`, and secret scan: passed.

## Runtime hygiene

- Removed task-owned PostgreSQL container `qn-task17-fix5`.
- Ports 8020 and 5445 and their protected services were not touched.
- Protected dirty files remained byte-identical:
  - `app-v2/src/quantinue/main.py`:
    `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
  - `app-v2/tests/unit/test_runtime_ownership.py`:
    `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`
