# DoneClaim — Todo 13 migration hardening

The two blockers reported against `a2a72be` are closed.

The migration no longer accepts a same-name partial event table merely because
a selected subset of column names exists. It validates the complete canonical
event-ledger column and constraint catalog and verifies the converged trigger
catalog. Any mismatch aborts the transaction.

Before append-only triggers are installed, existing normalized events and
evidence are audited for:

- event source equal to its raw document source;
- evidence raw version equal to its event raw version;
- evidence end offset no greater than normalized text length.

Invalid history causes an atomic, fail-loud migration. It remains editable for
operator correction because the new immutable triggers are not committed.
After correction, the migration is repeatable and converges to the fresh
catalog.

Evidence:

- `verification.md`
- `manual-qa.md`
