# Todo 1: active pipeline snapshots

Status: PASS

- Red phase: `tests/unit/test_active_run_snapshots.py` initially failed because `InMemoryRunStore.list_active` did not exist.
- Memory regression: `uv run pytest -q tests/unit/test_active_run_snapshots.py tests/unit/test_persistence_orchestration.py tests/unit/test_pipeline_resilience.py` passed: 20 tests.
- Static checks: scoped Ruff format/check and basedpyright passed with zero diagnostics.
- Disposable PostgreSQL: `sh scripts/test_postgres_integration.sh -q tests/integration/test_active_run_snapshots.py` passed: 21 tests. The runner used its ephemeral 554xx host port and cleaned up its container.
- Manual runtime driver: a claimed memory run with component `05` in `retrying` state produced `NVDA retrying 05`; the stable `TRANSIENT_HTTP_FAILURE` code remained observable and the injected raw provider text was absent from serialized snapshot output.

Contract outcome:

- `RunStore.list_active()` returns checkpoint-backed active snapshots only; terminal history remains on `list_recent()`.
- Snapshots retain run identity, ticker, cycle, completed stages, evidence trace, current status, and attempts.
- Attempts contain timestamps/status/stable error code only, never `error_message`.
