# DoneClaim — Todo 13 legacy upgrade recovery

Verdict: PASS.

The event migration now recognizes the exact original Todo 13 predecessor
catalog from `fe0e282`, including its missing normalized-source CHECK and
legacy raw-version immutability trigger. It accepts no broader weakened shape,
adds the missing canonical contract, replaces the legacy trigger, and
converges on repeated runs.

The operator recovery sequence for invalid rows protected by prior immutable
triggers is now regression-tested and explicit: after the atomic audit rejects,
drop only the normalized-event and evidence immutable triggers, repair the
reported lineage rows, and rerun the migration. The migration restores both
triggers. Provenance validation itself is never disabled.

Verification:

- The two verifier reproductions failed before this fix and pass afterward.
- The exact `fe0e282` schema upgraded on PostgreSQL 16 and the migration then
  succeeded a second time.
- A real `fe0e282` → `a2a72be` state with invalid legacy rows rejected
  atomically; repair was blocked before the narrow trigger step, succeeded
  afterward, and two migration reruns restored immutability.
- 19 focused event/schema tests passed twice (38 total).
- Ruff, basedpyright, compileall, `git diff --check`, and the secret scan passed.

Cleanup and isolation:

- The disposable 5490 container and temporary SQL/output files were removed.
- Ports 5490 and 8021 are free.
- The existing 8020 process remains PID 68620 with the same command.
- The 5445 database container remains
  `7381355c2f3154a229adb65fd15ca45fa53bdd0f16b00d4e1311a76e62461524`
  and still has no event tables.
- Unrelated dirty-file SHA-256 values remain
  `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
  and
  `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`.

Changed task files:

- `app-v2/db/migrations/mvp2.sql`
- `app-v2/tests/integration/test_event_storage_migration.py`
- this DoneClaim

Commit subject: `fix(events): 기존 사건 원장 업그레이드 복구`

Residual risk: the predecessor allowance is intentionally tied to the exact
PostgreSQL 16 catalog fingerprints of the canonical and `fe0e282` layouts.
