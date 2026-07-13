# Control-room detail visual QA verdict

## Scope and safe runtime

- Fresh captures were taken after the current dashboard/detail sources with a temporary Uvicorn process on `127.0.0.1:8015` only.
- Runtime configuration was memory database, mock broker, mock LLM, fixture data, and trading locked. Docker, PostgreSQL, `.env`, and `localhost:5432` were not accessed.
- `POST /api/runs` completed an NVDA 11-stage fixture run. A real browser form submission completed an MSFT 11-stage fixture run and returned to the dashboard.
- A legacy or failed detail snapshot is not reachable through the safe public runtime without injecting a store fixture; no product state was mutated solely to fabricate one.

## Captured state coverage

| Capture | Viewport | Route/state |
| --- | ---: | --- |
| `dashboard-1440.png` | 1440 | completed NVDA fixture run, details collapsed |
| `dashboard-1024.png` | 1024 | completed NVDA fixture run, details collapsed |
| `dashboard-768.png` | 768 | completed NVDA fixture run, details collapsed |
| `dashboard-390.png` | 390 | completed NVDA fixture run, details collapsed |
| `dashboard-1440-details-open.png` | 1440 | first native collection detail expanded |
| `dashboard-1024-form-run.png` | 1024 | completed MSFT run from real `/runs` form submission |

## Objective browser checks

- All four responsive base captures had document and body `scrollWidth == clientWidth`; no horizontal overflow.
- Four native `details` controls were found; click opened the captured collection summary.
- The allowed external source link had `href=https://example.invalid/fixture-news`, `target=_blank`, and `rel=noopener noreferrer`.
- Keyboard focus reached a native `summary`; its computed focus outline was a visible 3 px blue treatment with 2 px offset.
- Browser console and page-error collections were empty. Full structured observations are in `runtime-observations.json` and `form-run-observation.json`.

## Independent review lanes

| Lane | Verdict | Result |
| --- | --- | --- |
| Design-system and functional integrity | PASS | Real server-rendered DOM, semantic controls, responsive layout, native details, and safe-link behavior verified. |
| Visual fidelity and CJK precision | PASS | All six captures reviewed; no CJK clipping, unnatural phrase breaks, overlap, or horizontal overflow found. |

## Verdict: PASS

The fresh rendered surface visibly presents collection, strategist, and critic detail while preserving the existing operational visual system across 1440, 1024, 768, and 390 px.

## Cleanup

The temporary Uvicorn process on `127.0.0.1:8015` was stopped after capture. No runtime state, database, container, volume, network, or environment file was changed.
