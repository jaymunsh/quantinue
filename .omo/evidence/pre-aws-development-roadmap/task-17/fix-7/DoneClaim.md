# Todo 17 Fix 7 DoneClaim

## Result

The Fix 6 public event-analysis matrix retains its behavior while removing the
candidate-only basedpyright regression. The exact eight-file predecessor and
candidate commands both report 361 errors and 2 warnings, for a net delta of
zero errors and zero warnings. The candidate-only trigger-arbitration module
reports 0 errors and 0 warnings.

## Type boundary changes

- The optional atomic work-lease operation is represented by a runtime-checkable
  typed protocol instead of `getattr` and an `Any` return.
- The integration ledger-count query is parsed through a frozen Pydantic model
  with named SQL columns instead of iterating over untyped row values.
- The expected cancellation call result is explicitly discarded.

No ignore comments, `Any` casts, test deletion, or baseline changes were used.

## Verification

- Exact basedpyright predecessor (`15769ac`): 361 errors, 2 warnings.
- Exact basedpyright candidate: 361 errors, 2 warnings.
- Candidate-only arbitration basedpyright: 0 errors, 0 warnings.
- Fresh PostgreSQL 16 public matrix: 14 passed.
- Critical hostile scenarios: 9 passed, 5 deselected.
- Ruff on changed and arbitration Python files: pass.
- Python compileall on changed and arbitration Python files: pass.
- `git diff --check`: pass.
- Secret scan: no provider-token or private-key patterns detected.

## Hygiene

The task-owned PostgreSQL container used port 5490 only. Protected dirty
`main.py` and `test_runtime_ownership.py` were not edited or staged by Fix 7.
Ports 8020 and 5445 were not accessed.
