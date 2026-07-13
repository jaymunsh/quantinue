# Runtime Debug Journal — PostgreSQL terminal-detail rehydration

Started: 2026-07-13T00:00:00Z
Goal: Verify that terminal administrator detail survives disposable PostgreSQL persistence and rehydration, with non-web `sec://` retained as a non-clickable reference.

## Environment snapshot (Phase 0)

- Runtime: Python 3.11.15 via `uv run`; integration runner is `scripts/test_postgres_integration.sh`.
- Database: runner-created disposable `postgres:17-alpine` container on an auto-selected loopback port in 55400-55499 only. localhost:5432 and product Compose are out of scope and were not inspected or used.
- Existing direct runtime scenario: `tests/integration/test_domain_lifecycle_postgres.py` requests `/api/runs/{run_id}/detail` after persisted workflow completion.
- References read: debugging skill; `runtimes/python.md`; methodology `00-setup.md`, `02-investigate.md`, `08-qa.md`, `09-cleanup.md`.

## Hypotheses

1. [CONFIRMED] `PipelineRun.detail` is serialized into the PostgreSQL terminal-run JSON, rehydrated intact, and projected by the live API. Evidence: disposable-runner integration asserted all collection/strategy/critic fields after persistence.
2. [REFUTED] The terminal-run persistence codec omits or rejects the new detail shape, so a rehydrated run loses fields or fails parsing. Evidence: the exact terminal detail response assertion passed.
3. [REFUTED] `sec://` survives persistence but becomes a clickable `href` in the API projection. Evidence: the live response asserted `href: None` for `sec://filing/fixture-filing`.

## Artifacts and cleanup

- [x] Disposable PostgreSQL container created only by `scripts/test_postgres_integration.sh`; its EXIT trap completed on successful script exit.
- [x] No debug listener, temporary fixture, source instrumentation, environment override, localhost:5432 access, or product Docker/Compose resource was created or used.
- [x] This journal and `persistence-verdict.md` are intentional scoped audit evidence.

## Findings

### 2026-07-13T00:00:00Z — disposable PostgreSQL terminal-detail runtime

- Source: `sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py`
- Value: `20 passed in 9.13s`
- Runtime path observed: full pipeline → `PostgresRunStore` terminal persistence → PostgreSQL-backed ASGI app → `GET /api/runs/{run_id}/detail`.
- Verbatim asserted terminal response fragments: `"reference": {"label": "sec://filing/fixture-filing", "href": None}`, `"proposal": "buy"`, `"rationale": "기술·공시·뉴스 합의"`, `"verdict": "pass"`, `"layer": "gate"`.
- Interpretation: collection, strategy, and critic display fields survived durable read-back and API projection; `sec://` remained non-clickable.

### Manual QA — pipeline/API runtime

- Scenario: the persisted terminal-detail endpoint was used via the actual ASGI API after a disposable PostgreSQL-backed pipeline run.
- Command: `sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py`
- Observed output: `20 passed in 9.13s`
- Expected output: durable collection/strategy/critic detail and `sec://` exposed only as a readable label with no `href`.
- Result: pass.
