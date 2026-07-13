# F3 manual QA verdict

## Verdict

PASS

Confidence: high.

## Runtime isolation

- Checked-in Compose contract rendered with PostgreSQL published only as `127.0.0.1:5444:5432`, web as `127.0.0.1:8011:8000`, and the web service database URL ending in `@db:5432/quantinue`.
- A pre-existing listener occupied `8011`, so F3 used the evidence-only `compose-f3.override.yaml` to bind web to `127.0.0.1:18011:8000`; the PostgreSQL host port remained `5444`.
- `docker compose -p quantinue_f3_qa -f compose.yaml -f .omo/evidence/final-f3/compose-f3.override.yaml up --build --wait` exited 0. Both isolated services became healthy.
- Host port `5432` was never inspected, bound, or stopped.

## API and browser observations

- `curl --fail --silent --show-error http://127.0.0.1:18011/health` returned `status: ok`, `broker_mode: mock`, and `llm_mode: mock`.
- `POST /api/runs` for `NVDA` returned a completed mock run with 11 stages, `buy`, and a filled paper order. Its detail endpoint returned progress 11, 11 evidence records, and pending T+5 review.
- A real Playwright Chromium session filled `NVDA`, clicked `파이프라인 실행`, observed the redirect back to the control room, and verified the 01–11 stage ledger, evidence lineage, order/review panel, skip-link focus, reduced-motion behavior, and zero browser console errors.
- Completed views at 1440x1000, 1024x1000, 768x1000, and 390x844 had no document horizontal overflow, 11 stage records, and 11 evidence records.
- In the disposable F3 database only, stage 11 of the latest temporary run was marked `timed_out` with stable code `ROLE_TIMEOUT`. The live API reported a failed UI stage with a persisted checkpoint and timed-out attempt. The live dashboard rendered `FAILED`, `timed_out`, and `ROLE_TIMEOUT`, while omitting the QA-only raw payload.

## Fresh screenshots

- `live-completed-1440x1000.png`
- `live-completed-1024x1000.png`
- `live-completed-768x1000.png`
- `live-completed-390x844.png`
- `live-timed-out-1440x1000.png`
- `live-timed-out-390x844.png`

`live-browser-results.json` and `live-failure-results.json` contain the per-viewport DOM assertions. Direct inspection found no clipping, corrupted pixels, document overflow, or unnatural Korean wrapping. Long provenance values wrap inside narrow evidence cards.

## Independent reviews

- Pass A, design-system/functional integrity: PASS, high confidence, no blocking findings.
- Pass B, visual fidelity/CJK precision: PASS, high confidence, no blocking findings.

Both reviewers opened all six fresh screenshots. They confirmed semantic server-rendered UI rather than a raster substitute, responsive reflow, readable CJK content, safe failure redaction, and correct mobile badge/card behavior. The only note was non-blocking: the provenance ledger is necessarily tall and dense on a 390px full-page capture.

## Cleanup receipt

`docker compose -p quantinue_f3_qa -f compose.yaml -f .omo/evidence/final-f3/compose-f3.override.yaml down -v --rmi local --remove-orphans` removed the two F3 containers, F3 image, F3 network, and F3 volume. Follow-up checks returned no F3 Compose resources and no listeners on `5444` or `18011`. Temporary API payload files and the temporary debug journal were removed. Existing services, including the pre-existing `8011` listener, were not changed.
