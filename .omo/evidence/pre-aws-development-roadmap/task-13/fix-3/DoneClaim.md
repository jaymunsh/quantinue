# DoneClaim — Todo 13 catalog convergence fix 3

Verdict: PASS.

The PostgreSQL 16 migration now compares existing event-ledger constraints,
indexes, canonical defaults, functions, and triggers against a versioned
normalized catalog manifest. Same-named but behaviorally different objects
abort the transaction before replacement. Missing canonical functions and
triggers remain repairable after an audit failure, and two subsequent
migration runs converge to the fresh-schema fingerprint.

Verification:

- Baseline before the fix: 16 focused tests passed.
- Adversarial RED: the weakened same-name catalog and negative-span case were
  accepted by the prior migration.
- GREEN: 17 focused event/schema tests passed twice (34 total).
- Ruff, basedpyright, compileall, `git diff --check`, and the repository secret
  scan passed.
- Manual PostgreSQL 16 QA on `127.0.0.1:5490` observed atomic rejection with an
  unchanged rejected-state fingerprint, successful operator repair, two
  successful reruns, and an exact fresh/migrated catalog fingerprint match.
- Boundary SQL rejected negative evidence offsets, orphan evidence, a short
  summary, duplicate processing, and ordered processing without order lineage.
  Valid provenance plus cursor and receipt transitions succeeded.

ULTRAQA:

- Malformed rows/catalog: rejected.
- Cancel/resume and stale partial state: rollback followed by repair/rerun passed.
- Dirty worktree: unrelated file hashes stayed unchanged.
- Hung commands: Docker and test commands used bounded timeouts.
- Flake probe: the focused suite passed twice.
- Misleading output: direct catalog fingerprints and row assertions were used.
- Repeated interruption: audit failure, repair, and repeated rerun passed.
- Prompt injection: not applicable; the migration consumes no external prose.

Cleanup receipt:

- The disposable container and QA temporary files were removed.
- Ports 5490 and 8021 are free.
- The existing 8020 process (PID 68620) and command are unchanged.
- The 5445 database container identity is unchanged and still has no event
  tables.
- `app-v2/src/quantinue/main.py` SHA-256 remains
  `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`.
- `app-v2/tests/unit/test_runtime_ownership.py` SHA-256 remains
  `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`.

Changed task files:

- `app-v2/db/migrations/mvp2.sql`
- `app-v2/tests/integration/test_event_storage_migration.py`
- this DoneClaim

Commit subject: `fix(events): 사건 원장 카탈로그 완전 수렴`

Residual risk: the manifest intentionally pins PostgreSQL 16 normalized catalog
rendering; a future major PostgreSQL upgrade must regenerate and review it.
