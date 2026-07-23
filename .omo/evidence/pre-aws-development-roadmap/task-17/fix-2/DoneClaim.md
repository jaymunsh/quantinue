# Fix 2 done claim

Implemented a durable, owner-fenced rejudgement contract shared by event and
intraday analysis. The change closes cancellation gaps around committed claims,
uses a single ticker/persona cooldown namespace, distinguishes reused work from
new completion, bounds provider execution, and retains the latest idle runtime
telemetry.

Verification:

- Full unit suite: `719 passed`
- Relevant unit/PostgreSQL matrix: `178 passed`, repeated twice
- Critical cancellation/restart/timeout matrix: five cases repeated 10 times
- Real PostgreSQL distinct-event cooldown race: `1 passed`; one durable
  `AAPL/aggressive/claimed` row remained
- Migration applied twice to PostgreSQL 16
- Ruff: passed
- `compileall`: passed
- Focused basedpyright: 125 inherited errors, 0 warnings (no regression from
  Fix 1's recorded 184 errors, 2 warnings)

Database catalog evidence:

```text
tb_event_processing_receipt.owner_token:text:YES
tb_event_processing_receipt.result_payload:jsonb:YES
tb_rejudgement_cooldown:
  ticker:text:NO
  persona:text:NO
  status:text:NO
  owner_token:text:NO
  claimed_at:timestamp with time zone:NO
  completed_at:timestamp with time zone:YES
durable row:
  AAPL|aggressive|claimed|owner present|claimed_at present|completed_at absent
tb_llm_usage rows: 0
tb_order rows: 0
```

The task-owned PostgreSQL container and temporary diagnostic artifacts were
removed before commit. Protected foreign worktree modifications were neither
edited nor staged.
