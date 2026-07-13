# Todo 3: Live pipeline panel

## Delivered behavior

- The dashboard renders a live panel only when its newest safe run is `running` or `retrying`.
- The server-rendered baseline shows ticker, run ID, completed count, current canonical role, next canonical role, status, and only a redacted error code.
- When JavaScript is enabled, the panel polls same-origin `/api/runs` every 1.5 seconds. It changes only bounded text fields, doubles its interval after a failed status read up to 6 seconds, and clears the interval when a terminal state arrives.
- The panel uses a polite status announcement and retains the existing keyboard focus, reduced-motion, and responsive layout rules.

## Focused automated proof

`QUANTINUE_DATABASE_MODE=memory QUANTINUE_BROKER_MODE=mock QUANTINUE_LLM_MODE=mock QUANTINUE_DATA_MODE=fixture QUANTINUE_TRADING_ENABLED=false uv run pytest -q tests/test_live_progress_dashboard.py tests/unit/test_live_progress_api.py tests/test_web.py tests/test_dashboard_detail.py`

Result: `19 passed`.

The focused dashboard tests cover active-only rendering, canonical 05/06 labels, the inline safe polling contract, redaction, terminal pages omitting the script, and active-first ordering when a terminal and active run share the same minute timestamp.

## Chromium manual QA

An isolated memory/fixture/mock Uvicorn process on `127.0.0.1:8143` ran a deliberately delayed role 05. Chromium verified at 1440, 1024, 768, and 390 px that the active panel appeared with `05 공시 분석`, had no document overflow, advanced to terminal `완료`, and stopped its initiating page's follow-up polling interval. A JavaScript-disabled 390 px page retained the server-rendered current-role and announcement text. The mobile screenshot is `task-3-390.png` and the executable check is `task-3-browser.spec.js`.

`LIVE_PROGRESS_BASE_URL=http://127.0.0.1:8143 npx playwright test .omo/evidence/live-progress/task-3-browser.spec.js --reporter=line`

Result: `1 passed (10.5s)`.

## Equal-minute ordering repair

The initial `cycle_ts`-only sort preserved insertion order when an active and terminal run shared the minute used by new launches. That could select the terminal record as `latest` and suppress the live panel. A regression first reproduced the missing panel with a real in-memory terminal record and active snapshot at the same timestamp. The safe run composition now uses active status as the timestamp tie-breaker, so `running` and `retrying` records precede terminal history without changing the relative ordering of terminal records.

## Static proof and cleanup

- `uv run ruff format --check .` -> `157 files already formatted`
- `uv run ruff check .` -> pass
- `uv run basedpyright` -> `0 errors, 0 warnings, 0 notes`

The isolated Uvicorn process was stopped with SIGINT. Its memory store was discarded. No Docker, PostgreSQL, `localhost:5432`, `.env`, provider key, real broker, or real LLM was used.
