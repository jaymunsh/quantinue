# Todo 17 DoneClaim

## Delivered

- An accepted event now reuses the existing `AnalysisJob` strategist and critic
  contracts for the event ticker only.
- Every `(event_id, ticker, analysis:persona)` is claimed in
  `tb_event_processing_receipt` before the provider boundary.
- The receipt distinguishes an unbilled claim from a charged/ambiguous claim:
  `claimed + completed_at IS NULL` can be released, while
  `claimed + completed_at IS NOT NULL` fails closed after interruption.
- Duplicate events, the configured cooldown, and `BudgetedAnalyzer` refusals
  suppress further paid work. The same shared analyzer retains the daily hard
  cap and sell-side reservation.
- Evidence created before this deployment is also discovered and dispatched;
  no separate generic analysis or order path was introduced.

## Verification

- `130 passed` across event dispatch, daily/event analysis, ingestion runtime,
  job factory, LLM budget/cap/reservation, intraday rejudgement, and PostgreSQL
  event evidence/routing tests.
- Focused `basedpyright` for the new dispatcher, receipt repository, and its
  unit tests: `0 errors, 0 warnings`.
- Ruff on all Todo 17 production and test files: pass.
- `scripts/scan_secrets.sh`: no provider-token or private-key patterns.
- PostgreSQL integration used only disposable `postgres:16-alpine` on
  `127.0.0.1:5490`. It asserted the charged encoding directly, then proved a
  restart returns duplicate and a later related event is cooldown-skipped.
- Cancellation-after-charge unit QA proved one provider-bound call, no
  completion, no release, and therefore no silently retryable paid attempt.
- Prompt-like article text (`ignore all prior instructions`) remained bounded
  event evidence and did not alter routing or receipt behavior.

## Protected State

- `app-v2/src/quantinue/main.py` and
  `app-v2/tests/unit/test_runtime_ownership.py` were pre-existing dirty files
  and were not staged for this task.
- The live observer on port `8020` and production-like PostgreSQL on `5445`
  were inspected only and left unchanged.
- Two initially overlapping untracked files were integrated instead of
  discarded:
  `events/analysis.py` (initial SHA-256
  `700eea28cd2644bdf94f9c68a53eca2da411478c29ef7dd4dfcc2b3083168d65`)
  and `tests/unit/test_event_analysis.py` (initial SHA-256
  `cb4297a1a34274dc2308179584132ef13d9ef9cdecc96610692882f3aea241e2`).

## Residual Risk

- A charged-but-unfinished receipt intentionally requires operator
  reconciliation rather than automatic retry. This prefers avoiding duplicate
  paid analysis over automatic recovery from an ambiguous provider outcome.
- Strict whole-file typing still reports legacy errors in the pre-existing
  large `job_factory.py` and `roles/analysis/job.py`; the new Todo 17 modules
  and their contracts are clean under focused type checking.
