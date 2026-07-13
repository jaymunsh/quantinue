# Todo 4: lifecycle, persistence, and visual verification

Status: PASS

## Reproducible test-isolation repair

The initial bare `uv run pytest -q` inherited the operator's `.env` database mode.
Ten tests that construct default `Settings()` attempted the configured host `5444`
database and failed before their intended assertions.  The test safety fixture was
missing only `QUANTINUE_DATABASE_MODE=memory`.  Adding that existing safe test
default restored isolation without reading or changing `.env`.

The same red run also reproduced a separate composition regression:
`test_postgres_app_composes_due_review_route` did not mount the review route when
an in-memory run store was injected.  `create_app()` now composes the review runtime
whenever the explicit settings select PostgreSQL; run-store injection does not alter
that settings-level route contract.

Focused red-to-green proof:

```text
uv run pytest -q tests/test_web.py tests/unit/test_api_ticker_boundary.py \
  tests/unit/test_control_room_access.py tests/unit/test_review_route_composition.py \
  tests/unit/test_live_progress_api.py tests/test_live_progress_dashboard.py
37 passed
```

## Final automated gates

```text
uv run ruff format --check .                 157 files already formatted
uv run ruff check .                           PASS
uv run basedpyright                           0 errors, 0 warnings, 0 notes
uv run pytest -q                              385 passed, 18 expected skips
sh scripts/test_postgres_integration.sh -q    21 passed
sh scripts/test_compose_contract.sh           compose contract: PASS
```

The PostgreSQL command used only `scripts/test_postgres_integration.sh`'s
disposable runner.  No product Compose stack, `.env`, real broker/LLM, or host
`localhost:5432` resource was used.

## Runtime hypotheses and observations

1. **A running checkpoint can be observed before terminal completion.**
   Confirmed: an isolated memory/fixture/mock Uvicorn process on `127.0.0.1:8149`
   delayed canonical role `05` for 25 seconds.  The form returned `303` immediately;
   Chromium observed `05 공시 분석 · running` with pending `06 뉴스 분석`.
2. **The safe active projection survives both memory and PostgreSQL boundaries.**
   Confirmed: memory active/terminal/duplicate coverage is in the focused 37-test
   run, and the disposable PostgreSQL suite passed 21 tests including active snapshot
   integration.  Active snapshots expose a stable failure code only, never the raw
   `error_message` field.
3. **Client polling backs off safely and stops after terminal transition.**
   Confirmed: the delayed role completed to the terminal `완료` state in real
   Chromium; the initiating page made no additional `/api/runs` request after the
   post-terminal 1.8-second observation window.  Browser console and page-error
   collections were empty.

## Fresh Chromium evidence

```text
LIVE_PROGRESS_BASE_URL=http://127.0.0.1:8149 \
  npx playwright test .omo/evidence/live-progress/task-4-browser.spec.js \
  --reporter=line --workers=1
1 passed (27.0s)
```

- `task-4-1440-active.png`, `task-4-1024-active.png`, `task-4-768-active.png`,
  `task-4-390-active.png`: live delayed role at all required responsive widths.
- `task-4-390-no-js.png`: server-rendered no-JavaScript baseline.
- `task-4-1440-terminal.png`: terminal presentation after polling transition.

Every required viewport had `scrollWidth <= clientWidth`; the live panel was visible
while running, showed the current/next canonical roles, and retained the safe
announcement text.  The browser test also asserted no console/page errors.

## Cleanup

- Stopped all temporary `8149` Uvicorn instances; the memory stores were discarded.
- Removed the failed-run Playwright `test-results` artifact before recording this
  evidence.
- No Docker container, volume, network, product Compose service, `.env`, or secret
  was created, changed, or retained.
