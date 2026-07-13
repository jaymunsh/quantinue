# H2 Runtime Audit — active checkpoint projection

Status: CONFIRMED

## Scope

- Runtime surface: real FastAPI `TestClient` against `GET /api/runs`.
- Storage: a fresh `InMemoryRunStore` only.
- Excluded: Docker, PostgreSQL, `.env`, ports 5432/5444, external model/broker/data calls, and persistent configuration changes.

## Hypotheses and observations

1. **Active canonical work determines current and next canonical stages.**
   - Setup: component `05` completed a failed first attempt (stable code `TRANSIENT_HTTP_FAILURE`), then a retrying second attempt; noncanonical component `99` was appended afterward. A terminal run with the identical ticker and minute was also present.
   - Observed JSON: HTTP `200`; ordered statuses `['running', 'completed']`; active `current_stage={'component': '05', 'name': '공시 분석', 'status': 'retrying'}`; `next_stage={'component': '06', 'name': '뉴스 분석', 'status': 'pending'}`.
   - Result: confirmed. The later noncanonical record did not displace canonical `05`; only canonical `06` was selected next.

2. **A noncanonical-only active attempt falls back safely to the first canonical stage.**
   - Setup: fresh active run containing only component `99` in `running` state.
   - Observed JSON: HTTP `200`; `current={'component': '01', 'name': '1차 스크리너', 'status': 'pending'}`; `next={'component': '02', 'name': '기술 분석', 'status': 'pending'}`; `noncanonical_in_current_or_next=False`.
   - Result: confirmed. No `StopIteration`, 500 response, or noncanonical current/next projection occurred.

3. **Raw failure text is not returned, including the same-minute terminal-plus-active tie.**
   - Setup: injected a synthetic raw-provider-error marker into the failed attempt before creating the retrying attempt and same-minute terminal record.
   - Observed JSON: `sentinel_present=False`, `raw_error_field_present=False`, `stable_failure_code_present=True`.
   - Result: confirmed. The operator-visible stable failure code survives, while the raw message and its field do not.

## Cleanup

- The two audit processes were one-shot `uv run python` commands and exited successfully.
- Their memory stores were process-local and discarded at exit.
- No listener, temporary source file, database object, container, volume, network, `.env`, or secret was created or changed.

## Verdict

**CONFIRMED** — the live control-room projection reports canonical active/current-next progress, handles a noncanonical attempt without failure, ranks the active run above a same-minute terminal run, and redacts raw attempt errors at the actual HTTP boundary.
