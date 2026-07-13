# Debug Journal — H1 transport retry audit
Started: 2026-07-13T08:13:09+09:00
Goal: Determine whether httpx2 ConnectError, ReadError, or RemoteProtocolError bypass retry or leave stuck attempts.

## Environment snapshot (Phase 0)
- Runtime: CPython 3.11.15 via `uv run` (`.venv/bin/python3`), httpx2 2.5.0, AnyIO.
- Entry: focused pytest and deterministic inline AnyIO runner.
- Ports / sockets: compose `app-db-1` healthy on container-only 5432; no host listener observed at 5444; existing web on 8011.
- Git HEAD: `ba0c742`; working tree already contains user/other-agent changes and many untracked implementation/evidence files.
- References read: debugging `SKILL.md`, `runtimes/python.md`, `methodology/00-setup.md`, `methodology/02-investigate.md`; programming `SKILL.md`, `references/python/README.md`.

## Hypotheses
1. [REFUTED] All three concrete errors retry within budget and close their attempts in memory and PostgreSQL.
2. [CONFIRMED IN POSTGRESQL] Exhaustion closes/redacts the attempt, but explicit resume crashes before a new attempt because the failed payload is not a `PipelineContext`.
3. [CONFIRMED] PostgreSQL diverges from memory at failed-run resume; no attempt row remains running, but resumability is broken by payload decoding.

## Failed hypothesis round counter
- Round 1: decisive; H1 confirmed for PostgreSQL resume, so PASS is prohibited.

## Artifacts to revert
- [x] `.omo/evidence/debug-h1-runtime.txt` — retained as requested evidence.
- [x] `.omo/evidence/debug-h1-report.md` — retained as requested evidence.
- [x] PostgreSQL rows — isolated inside disposable container; container removed.
- [x] Disposable container and dynamic port — EXIT trap completed; no matching container or listener remains.

## Findings

### Memory runtime
- All three success cases: `[(1, 'retrying', 'TRANSPORT_FAILURE', 'provider transport failed', True), (2, 'completed', None, None, True)]`, `running_count=0`, `raw_present=False`.
- Exhaust/resume: persisted `failed/TRANSPORT_FAILURE/provider transport failed`; resume `completed same_run_id=True`, `running_count=0`.

### Disposable PostgreSQL runtime
- All three first-retry cases matched memory and left zero running attempts.
- Exhaustion persisted closed/redacted. Resume failed at `postgres.py:114` with `PipelineContext.request Field required` before attempt 2.

## Root cause (confirmed 2026-07-13T08:15:00+09:00)
- Mechanism: `_record_failure` passes a `PipelineRun` to `finish_run`; PostgreSQL overwrites `payload` with that terminal/public shape. A resumable claim unconditionally parses the payload as internal `PipelineContext`, whose required `request` field is absent.
- Evidence: traceback at `src/quantinue/db/postgres.py:114`; overwrite at `src/quantinue/db/postgres.py:230`.
- Toggle proof: `PipelineRun` payload produced `('request',) missing`; `encode_context(PipelineContext)` produced `valid_context=True same_run_id=True`.
- Fix scope: preserve resumable context separately or avoid replacing it with terminal payload; add real-PG transport exhaustion/resume regression coverage.

## Final fix
- Read-only audit; no product source edit authorized.
