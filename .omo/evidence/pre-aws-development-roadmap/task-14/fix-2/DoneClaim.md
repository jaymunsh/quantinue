# Todo 14 fix-2 Done Claim

## Claim

- `JobRunner` invokes incremental event collection only during canonical NYSE
  premarket or regular sessions.
- Weekends, NYSE holidays, and weekday overnight ticks cause zero event runtime
  calls.
- `EventIngestionExecutor.sources` accepts covariant mappings, eliminating the
  verifier-reported `job_factory.py:937` dictionary invariance error.

## Implementation evidence

- Reused `NyseCalendar.current_session()` and `Session`; no custom market calendar
  logic was introduced.
- Added a structural `EventRuntime` boundary so the scheduler depends only on the
  asynchronous `tick(datetime)` contract.
- Added `test_event_runtime_session_gate.py`, exercising a Saturday, New Year's
  Day, weekday overnight, premarket, and regular-session tick through the real
  `JobRunner`.

## Verification

- Disposable PostgreSQL 16: `127.0.0.1:5490`, database `contracts`.
- Focused unit/integration suite, pass 1: `15 passed`.
- Focused unit/integration suite, pass 2: `15 passed`.
- JobRunner/JobFactory regression suite: `45 passed`.
- Final session-gate plus JobRunner/JobFactory suite: `46 passed`.
- Ruff on fix-2 production and test files: `All checks passed!`.
- Basedpyright on Todo 14 event/config/test scope: `0 errors, 0 warnings, 0 notes`.
- Python compileall on changed production/test scope: exit 0.
- `git diff --check`: exit 0.
- The broader pre-existing JobRunner/JobFactory type check still reports 49
  SQLAlchemy/unknown-type errors. The fix-1-specific `job_factory.py:937`
  invariance diagnostic is absent.

## Isolation

- Protected dirty files were not edited or staged:
  - `app-v2/src/quantinue/main.py`:
    `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
  - `app-v2/tests/unit/test_runtime_ownership.py`:
    `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`
- Existing listeners on `127.0.0.1:5445` and `127.0.0.1:8020` were observed
  and left untouched.
