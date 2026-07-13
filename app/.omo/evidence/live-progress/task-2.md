# Todo 2: asynchronous launch and safe active API projection

## Contract delivered

- `POST /runs` validates and returns `303 /` without waiting for pipeline completion.
- Existing `POST /api/runs` remains synchronous and returns the terminal `PipelineRun` contract.
- New `POST /api/runs/async` returns `202` with only `accepted`, ticker, and cycle timestamp.
- App lifespan owns an AnyIO task group. A deterministic run key has at most one owned child task; shutdown cancels children and task-group exit awaits cleanup.
- `GET /api/runs` and `GET /api/runs/{run_id}` now include redacted active snapshots alongside terminal runs, with `current_stage` and `next_stage`. Raw error messages remain absent.

## Focused automated proof

`uv run pytest -q tests/unit/test_live_progress_api.py` → `5 passed`

The delayed role test observed all of: immediate 202 acknowledgement, durable running component `05` (공시 분석), next component `06` (뉴스 분석), duplicate acknowledgement without a second task, and the terminal completed transition. Invalid form input still redirects without a launch. A blocking-role lifecycle test confirms shutdown cancels and awaits the owned child task.

## Verifier regression repair

An active persisted attempt with noncanonical component `99` previously caused `GET /api/runs` to raise `StopIteration` while calculating the next stage. The focused TestClient regression first reproduced that 500 path, then verified the repaired endpoint returns `200`, omits raw errors, ignores `99` for progress selection, and falls back to canonical `01` with next `02`.

## Regression and static proof

- memory-mode web/control-room/active-snapshot/pipeline regression selection: `45 passed`
- `ruff format --check` and `ruff check`: pass
- `basedpyright` on changed Python surfaces: `0 errors, 0 warnings`
- module size: `main.py` 234 lines; presentation split to 190 lines.

## Minimal live HTTP proof and cleanup

An isolated memory/fixture/mock Uvicorn process on `127.0.0.1:8137` returned `303` for form launch and `202` with `accepted: true` for `/api/runs/async`; the safe list endpoint returned the completed projection. The process was stopped with SIGINT and its memory state was discarded. No Docker, PostgreSQL, localhost:5432, `.env`, credentials, or real broker/LLM calls were used.
