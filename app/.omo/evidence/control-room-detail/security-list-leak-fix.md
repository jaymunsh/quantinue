# Security fix — `/api/runs` safe projection

## Finding and correction

The generic run-list route serialized persistence-domain `PipelineRun` objects directly.
Those objects retain administrator detail for durable storage, so the route could bypass the
existing redacted control-room projection. The route now returns `list[ControlRoomRun]` and
projects every listed run with its safe attempt view before serialization.

## TDD evidence

1. Red: `uv run pytest tests/unit/test_api_terminal_detail.py::test_terminal_detail_list_api_projects_only_redacted_run_views -q`
   failed because the list response had raw terminal-detail reference strings and no control-room
   projection fields.
2. Green: the same test passed after the route began returning the shared projection.

## Verification

```text
uv run pytest tests/unit/test_api_terminal_detail.py tests/test_web.py -q
24 passed

uv run ruff format --check src/quantinue/main.py tests/unit/test_api_terminal_detail.py
2 files already formatted

uv run ruff check src/quantinue/main.py tests/unit/test_api_terminal_detail.py
All checks passed!

uv run basedpyright src/quantinue/main.py tests/unit/test_api_terminal_detail.py
0 errors, 0 warnings, 0 notes
```

## Manual TestClient proof

An in-memory `TestClient` request to `GET /api/runs` returned `200 []`. The focused regression
then exercised a populated run through the same route and proved that credential-bearing,
control-scheme, and non-web raw reference markers were absent while the safe run identifier and
sanitized reference labels remained available.

## Scope and cleanup

No database, Docker resource, environment file, external service, or host `localhost:5432`
resource was accessed. No cleanup was needed.
