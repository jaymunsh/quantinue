# Task 4 — control-room latest-run detail brief

## Delivered

- Added a server-rendered `dashboard_brief.html` partial immediately before the generic evidence ledger.
- The brief shows disclosure/news collection records, score comparison, safe source references,
  strategist proposal/gate/conviction/blockers/rationale, and critic verdict/layer/rationale.
- Long summary and rationale text uses native `details`; safe `http(s)` destinations are the only
  clickable sources and open with `target="_blank" rel="noopener noreferrer"`.
- Empty, legacy, failed, and blocked snapshots retain an explicit unavailable state instead of
  fabricated detail.
- Added the reusable `decision-brief` primitive to `DESIGN.md`; it preserves the existing
  border-led GitHub-like operational surface and uses only existing tokens.

## TDD and focused verification

1. Red: `uv run pytest tests/test_web.py -q -k 'collection_to_critic or legacy_detail'` failed
   twice because the dashboard lacked the new brief and legacy-state copy.
2. Green: `uv run pytest tests/test_dashboard_detail.py -q` → `2 passed`.
3. Web surface with deterministic safe runtime modes:

```text
QUANTINUE_DATABASE_MODE=memory QUANTINUE_BROKER_MODE=mock \
QUANTINUE_LLM_MODE=mock QUANTINUE_DATA_MODE=fixture \
QUANTINUE_TRADING_ENABLED=false uv run pytest tests/test_web.py \
  tests/test_dashboard_detail.py -q
11 passed in 1.40s
```

4. Static checks:

```text
uv run ruff format --check tests/test_dashboard_detail.py tests/test_web.py
2 files already formatted
uv run ruff check tests/test_dashboard_detail.py tests/test_web.py
All checks passed!
uv run basedpyright tests/test_dashboard_detail.py tests/test_web.py
0 errors, 0 warnings, 0 notes
```

## Manual runtime proof and cleanup

- Started a temporary Uvicorn process on `127.0.0.1:8014` with memory database, mock broker,
  mock LLM, fixture data, and trading locked.
- Real `POST /api/runs` completed an 11-stage fixture run; real `GET /` rendered the brief,
  both collection cards, strategist and critic panels, native `details`, and the validated
  external link protection attributes.
- The temporary server received an interrupt and completed shutdown cleanly. Temporary response
  files were removed. Docker, PostgreSQL, `.env`, and `localhost:5432` were not accessed.

## Accessibility and responsive inspection

- The new partial retains semantic headings, articles, `dl`, native `details`, visible focus
  styling for links and summaries, existing reduced-motion policy, and `overflow-wrap` for long
  references/rationale.
- CSS uses existing 900 px and 640 px breakpoints: decisions collapse at 900 px and collection
  cards collapse to one column at 640 px, with no fixed-width child introduced.
- Browser visual inspection could not execute because the available in-app browser runtime
  returned exactly `No browser is available`. This is an environment tooling blocker, not a
  product failure; TestClient rendering and a real minimal HTTP runtime were completed instead.

## Scope

- No role, core terminal contract, API projection, scheduler, Docker, database, environment,
  or trading code was changed.
