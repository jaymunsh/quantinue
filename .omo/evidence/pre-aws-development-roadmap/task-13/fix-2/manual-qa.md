# Todo 13 migration hardening manual QA

Disposable PostgreSQL 16 container: `quantinue-task13-fix2`

Host port: `127.0.0.1:5490`

Matrix:

- `fe0e282` schema followed by current migration twice matched the current fresh
  schema-only dump: `valid_upgrade_catalog_equal=true`.
- A raw-document table containing the old guard's three selected columns but
  missing the rest of its canonical contract was rejected:
  `partial_rejected_rc=3 atomic_rollback=t`.
- Contradictory existing event source, wrong evidence raw version, and
  out-of-range span were rejected before new immutable triggers were installed:
  `badrows_rejected_rc=3 new_immutable_triggers=0`.
- After explicit operator correction, migration and rerun succeeded:
  `operator_recovery_and_rerun=true`.

Cleanup:

- `quantinue-task13-fix2` absent.
- Port 5490 free.
- Ports 5445 and 8020 untouched.
