# Task 5 — persistence, responsive UI, and full regression gates

## PostgreSQL persistence and API rehydration

Added a disposable-PostgreSQL assertion to
`tests/integration/test_domain_lifecycle_postgres.py` after the real fixture
01–11 pipeline run. The persisted terminal run is re-read through
`GET /api/runs/{run_id}/detail` and must preserve all bounded collection,
strategy, and critic values. The same proof checks that `sec://` remains a
visible non-link and that the fixture HTTPS reference is the only clickable
source.

Focused disposable command, with deterministic mock/fixture modes:

```text
env QUANTINUE_DATABASE_MODE=postgres QUANTINUE_BROKER_MODE=mock \
  QUANTINUE_LLM_MODE=mock QUANTINUE_DATA_MODE=fixture \
  QUANTINUE_TRADING_ENABLED=false \
  sh scripts/test_postgres_integration.sh -q \
  tests/integration/test_domain_lifecycle_postgres.py -k persists_real_domain_ids
1 passed, 19 deselected
```

## Runtime regression found and fixed

The first disposable run exposed `PydanticUndefinedAnnotation: StrategyOutput`
before role 01. Three hypotheses were tested: an unresolved
`TYPE_CHECKING`-only forward reference, adapter construction/import order, and
another new detail annotation. Runtime probes showed exactly two unresolved
names (`StrategyOutput`, `CriticVerdict`); supplying both to the adapter
namespace made JSON round-trip succeed. The durable fix is runtime imports in
`quantinue.core.contracts`, so the global context adapter resolves them without
caller-dependent namespace injection.

Red to green:

```text
uv run pytest -q tests/unit/test_roles_01_04_contracts.py -k checkpoint
before: PydanticUserError, adapter not fully defined
after: 1 passed, 35 deselected
```

## Fresh Chromium QA

Two isolated in-memory mock/fixture Uvicorn surfaces ran only on
`127.0.0.1:8015` (completed run) and `127.0.0.1:8016` (blocked empty-detail
snapshot). Playwright drove the form, opened the critic disclosure, verified
the safe HTTPS link, the visible non-web reference, blocked fallback copy,
browser-console/page errors, and document overflow at every required viewport.

```text
npx playwright test .omo/evidence/control-room-detail/task-5-browser.spec.cjs --workers=1 --reporter=line
8 passed
```

Fresh artifacts:

- `task-5-completed-{1440x1000,1024x1000,768x1000,390x844}.png`
- `task-5-blocked-{1440x1000,1024x1000,768x1000,390x844}.png`

The first visual pass found a focused skip-link captured over completed mobile
content. The capture driver now returns focus to the ticker before each resting
full-page capture; it was rerun 8/8. Two independent reviewers then returned
PASS: the refreshed screenshots have no horizontal overflow, clipping, CJK
breakage, or skip-link overlap.

## Final gates

```text
uv run ruff format --check .  -> 149 files already formatted
uv run ruff check .           -> All checks passed
uv run basedpyright           -> 0 errors, 0 warnings, 0 notes
uv run pytest -q              -> 373 passed, 17 expected skips
sh scripts/test_postgres_integration.sh -q -> 20 passed
sh scripts/test_compose_contract.sh         -> compose contract: PASS
```

The disposable runner owned its database container and cleaned it through its
exit trap. Product Compose was not run; the Compose command rendered only its
checked-in configuration. The later bare-command amendment below replaces the
initial explicit-environment invocation with durable test-runner isolation.

## Cleanup receipt

- Sent an interrupt to the two task-owned Uvicorn processes; both completed
  graceful shutdown.
- Confirmed no listeners remained on `127.0.0.1:8015` or `127.0.0.1:8016`.
- Removed the temporary blocked-state Python harness and the session debug
  journal; retained only the repeatable browser spec and screenshot evidence.
- No `.env` file, secret, host `localhost:5432`, product Docker container,
  volume, or network was inspected, used, stopped, or changed.

## Amendment — bare-command environment isolation

An independent verifier found that the required bare commands still inherited
the operator's `.env`: bare `uv run pytest -q` observed a local LLM model in
the YAML-default test, and bare `sh scripts/test_postgres_integration.sh -q`
selected public market data during the review path and failed on an unexpected
candle CSV shape.

Three runtime hypotheses were evaluated:

1. The PostgreSQL runner sets only its disposable database URL, allowing public
   data mode to reach the review runtime. Confirmed by the bare runner's
   `KeyError: 'Date'` in `http_source._candle_rows`.
2. `Settings()` in the policy-default test is intentionally `.env`-aware, so
   the user local model overrides the YAML default. Confirmed by the bare test
   returning `qwen3.6:35b-a3b-nvfp4` instead of `qwen2.5:7b`.
3. Product configuration precedence must change. Rejected: controlled test
   mode values make both exact failures pass while normal application `.env`
   precedence remains unchanged.

The minimal boundary fix is test isolation only:

- `tests/conftest.py` supplies fixture/mock/test-default environment values
  before test modules load, unless explicit real-key tests opt in.
- `scripts/test_postgres_integration.sh` exports the same safe fixture/mock
  modes while its disposable database exists.

Red to green:

```text
uv run pytest -q tests/unit/test_pipeline_policy.py::test_pipeline_yaml_owns_model_defaults_unless_environment_overrides
before: 1 failed (local model leaked from .env)
after:  1 passed

sh scripts/test_postgres_integration.sh -q -x
before: 1 failed, 4 passed (public candle parser KeyError)
after:  20 passed
```

Fresh required bare gates after the fix:

```text
uv run ruff format --check .  -> 149 files already formatted
uv run ruff check .           -> All checks passed
uv run basedpyright           -> 0 errors, 0 warnings, 0 notes
uv run pytest -q              -> 373 passed, 17 expected skips
sh scripts/test_postgres_integration.sh -q -> 20 passed
sh scripts/test_compose_contract.sh         -> compose contract: PASS
```

The runner's exit trap removed its task-owned disposable PostgreSQL container.
No product Compose resource, host `localhost:5432`, `.env`, or secret was
inspected or changed. The temporary debug journal was removed after this
amendment.
