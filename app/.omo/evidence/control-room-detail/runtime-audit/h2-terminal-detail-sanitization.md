# H2 Runtime Audit — terminal-detail sanitization

## Verdict

**CONFIRMED — PASS**

## Runtime evidence

Two independent in-memory/mock FastAPI applications were created with `TestClient(create_app(store=...))`:

1. terminal detail containing a credential-bearing HTTP URL;
2. terminal detail containing an ASCII-control-character URL.

For each application, the terminal-detail API, control-room API, and server-rendered dashboard returned HTTP 200. The synthetic sensitive marker was absent from every response body. The hostile reference had `href: null`; its dashboard raw form was absent. The credential-bearing case retained only a credential-free label, while the control-character case became `invalid reference`.

An approved HTTPS reference in the same run remained clickable in the API and dashboard, and its rendered anchor included `target="_blank"` and `rel="noopener noreferrer"`.

Focused regression coverage also passed: `uv run pytest -q tests/unit/test_api_terminal_detail.py tests/test_dashboard_detail.py` → `17 passed`.

## Post-fix extension — list endpoint

**CONFIRMED — PASS**

After the `/api/runs` projection fix, the same live-application probe was rerun with three independent hostile references: credential-bearing HTTP, ASCII-control-character, and non-web (`javascript:`) input. Each probe called all four surfaces:

- `GET /api/runs/{id}/detail`
- `GET /api/runs/{id}`
- `GET /api/runs`
- `GET /`

All four responses returned HTTP 200 in all three cases. The synthetic marker was absent from every response body, including the list response. Both the detail endpoint and the list projection returned `href: null` for each hostile reference and the expected safe label. The dashboard still omitted hostile raw references. An approved HTTPS reference in each probe remained a guarded dashboard anchor.

Focused regression confirmation after the projection change: `uv run pytest -q tests/test_web.py tests/unit/test_api_terminal_detail.py tests/test_dashboard_detail.py` → `26 passed`.

## Constraints and cleanup

- No Docker, PostgreSQL, `.env`, external network, or localhost:5432 was used.
- The audit used only process-local `InMemoryRunStore` state; processes exited after each assertion run.
- No temporary scripts, listeners, or debug instrumentation remain. The companion journal records the first fixture-coverage retry and cleanup without containing the marker or a credential.
