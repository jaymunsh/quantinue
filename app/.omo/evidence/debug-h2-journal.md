# Debug Journal — H2 lineage runtime audit

Started: 2026-07-13T00:00:00+09:00
Goal: Determine whether public-source/LLM lineage or T+5 review metadata is lost or stale across JSON, PostgreSQL, API, and dashboard composition.

## Environment snapshot (Phase 0)

- Runtime: CPython project; host `/usr/bin/python3` is 3.9.6; project launcher and virtual environment pending manifest inspection.
- Ports: no listener on host 5444 at assessment; existing unrelated host 5432 container `pf-postgres` must not be touched.
- Git HEAD: `ba0c742`; workspace is already dirty/untracked from parent implementation work.
- References read: debugging `SKILL.md`, `runtimes/python.md`, `methodology/00-setup.md`, `methodology/02-investigate.md`, `methodology/partial-runtime-evidence.md`.

## Hypotheses

1. [REFUTED for pipeline payload; CONFIRMED for normalized source/T+5 projections] Serialization preserves every modeled trace value exactly, but normalized source and review-snapshot rows are not self-contained evidence records.
2. [CONFIRMED in part] Model/prompt/policy/hash and direct parents survive exactly; provider identity is absent from the producer contract and therefore absent from PostgreSQL/API/UI.
3. [REFUTED] Failure snapshot is safely redacted and observable; T+5 updates persisted and appeared fresh in API/dashboard.
4. [CONFIRMED] The remaining relational losses are projection-boundary behavior, while provider identity is missing before the projection.

## Failed hypothesis round counter

- Round 1: decisive; no Oracle Triple threshold reached.

## Artifacts to revert

- [x] Compose project `debug-h2-20260713` removed with volume/network; host 5444 verified free.
- [x] Temporary runtime scripts/logs under `/tmp/debug-h2-*` removed; glob verified empty.
- [x] Temporary Uvicorn server on `127.0.0.1:18082` stopped; port verified free.
- [x] Playwright script and screenshot removed after recording observations.
- [x] Audit evidence files `.omo/evidence/debug-h2-*` retained as requested deliverables, not product modifications.

Cleanup verification: unrelated `pf-postgres` remained running on host 5432 with its original published ports.

## Findings

### 2026-07-13 — full runtime chain
- Source: `/tmp/debug-h2-runtime.py` against Compose project `debug-h2-20260713`.
- Value: producer/PostgreSQL normalized equality `true` for all 11 terminal traces; component-06 checkpoint held the exact first six traces.
- Value: provider-field presence `{"producer":false,"postgres":false,"api":false}`.
- Value: failure DB attempt `failed / UNEXPECTED_ROLE_FAILURE / unexpected role failure`; raw injected secret absent from API/dashboard.
- Value: T+5 processor `completed`, offsets `[1,2,3,4,5]`; API review outcome `hit`, return summary `0.552%`.

### 2026-07-13 — browser QA
- Source: Chromium/Playwright at `http://127.0.0.1:18082/`.
- Value: HTTP 200; run ID/source/model/prompt/policy/hash/direct-parent/review checks all `true`; errors `[]`.

## Final fix

Read-only audit: no product fix authorized.
