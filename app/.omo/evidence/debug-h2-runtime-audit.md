# H2 runtime audit — lineage across wire, PostgreSQL, API, and dashboard

Date: 2026-07-13 (Asia/Seoul)
Verdict: **FAIL — H2 is confirmed in part.** PASS was permitted only if the loss/staleness hypothesis was fully refuted.

## Runtime scenario

- Disposable PostgreSQL: Compose project `debug-h2-20260713`, host `127.0.0.1:5444` → container `db:5432`.
- Public-source boundary: the real `HttpMarketData` adapter consumed five responses through `httpx2.MockTransport`, with unique source URLs/content.
- LLM boundary: one injected analyzer returned unique model, prompt, policy, and 64-character hash sentinels.
- Full 01–11 pipeline persisted through `PostgresRunStore`.
- A separate failing run persisted a redacted attempt snapshot.
- `ReviewProcessor` captured five due sessions and finalized T+5.
- FastAPI detail was read through ASGI; the dashboard was additionally loaded in Chromium through Playwright.

Canonical run ID: `7474581d782041a99107c2e7e6285a9d`.

## Refuted portions: values preserved exactly

Producer `PipelineRun.evidence_trace`, `pipeline_runs.payload`, GET `/api/runs/{run_id}`, and the rendered dashboard agreed on all modeled lineage fields checked:

| Component | Exact observed values |
|---|---|
| 01 | `nasdaq-screener`; `https://api.nasdaq.com/h2-screener?audit=unique`; observed/captured `2026-06-01T20:00:00Z`; confidence `0.9`; execution/run ID `747458…5a9d` |
| 05 | `sec-submissions`; `https://data.sec.gov/h2-sec/0001045810?audit=unique`; model `wire-model-disclosure-h2`; prompt `prompt-disclosure-h2`; policy `policy-disclosure-h2`; hash `111…111` (64); direct parent `…:04:market` |
| 06 | `rss`; `https://source.example/h2-news-unique`; observed `2026-06-01T19:59:00Z`; captured `20:00:00Z`; confidence `0.9`; model/prompt/policy `wire-model-news-h2` / `prompt-news-h2` / `policy-news-h2`; hash `222…222`; direct parent `…:05:disclosure` |
| 07 | confidence `0.776`; model/prompt/policy `wire-model-strategy-h2` / `prompt-strategy-h2` / `policy-strategy-h2`; hash `333…333`; exactly three direct parents: components 02, 05, 06 |
| 08 | confidence `0.824`; model/prompt/policy `wire-model-critic-h2` / `prompt-critic-h2` / `policy-critic-h2`; hash `444…444`; direct parent component 07 |
| 10 | direct parent component 09; broker source/reference and order evidence ID preserved |
| 11 | direct parent component 10 preserved |

All 11 producer evidence objects were byte-value equivalent after JSON normalization to the 11 objects read from `pipeline_runs.payload`. The component-06 checkpoint contained the exact first six traces, proving checkpoint fidelity rather than only terminal rewrite fidelity.

Canonical consumed source rows also existed with unique values:

- `tb_disclosure`: filing `H2-ACCESSION-UNIQUE`, filed at `2026-06-01 00:00:00+00`, summary `8-K h2.htm`.
- `tb_news`: key `https://source.example/h2-news-unique`, published at `2026-06-01 19:59:00+00`, summary `H2 wire snippet`.

## Confirmed loss

### 1. LLM provider identity is absent end-to-end

Runtime presence checks were all false:

```json
{"producer": false, "postgres": false, "api": false}
```

The injected analyzer could identify unique models but the trusted `AnalysisMetadata` / `RoleEvidenceTrace` contract has no provider field. Therefore OpenAI versus local OpenAI-compatible provenance cannot be represented, persisted, or shown. This loss occurs before serialization; PostgreSQL and API are faithfully preserving an already-incomplete object.

### 2. Canonical source tables are intentionally lossy projections

The terminal/checkpoint JSON retains complete public provenance, but relational `tb_disclosure` / `tb_news` rows do not independently retain the full evidence object (execution ID, captured time, direct parents, model/prompt/policy/hash). They remain correlatable through the pipeline payload/domain joins, not self-contained audit records. This is a projection boundary, not a JSON codec corruption.

### 3. T+5 snapshots lack evidence-grade lineage fields

The processor persisted exact due closes and dates but each snapshot exposed only `day_offset`, `price_date`, `close`, and generic source `market_data`. It did not persist a concrete source reference, captured timestamp, confidence, evidence ID, or parents. The final review itself was fresh and propagated correctly.

## Failure snapshot

The deliberately thrown raw text `SECRET-H2-RAW-ERROR-MUST-NOT-LEAK` was not present in API or dashboard output. PostgreSQL retained only:

```json
{"status":"failed","code":"UNEXPECTED_ROLE_FAILURE","message":"unexpected role failure"}
```

GET detail exposed component 01 as failed, attempt 1, failure code `UNEXPECTED_ROLE_FAILURE`, zero checkpoints, and no fabricated evidence. This behavior is correct and not stale.

## T+5 result and read-back

Processor result: `completed`, captured offsets `[1,2,3,4,5]`.

Persisted closes:

- T+1 `2026-06-02` → `151.02`
- T+2 `2026-06-03` → `151.03`
- T+3 `2026-06-04` → `151.04`
- T+4 `2026-06-05` → `151.05`
- T+5 `2026-06-08` → `151.08`

Persisted final review: `ret_5d=0.552412645590682196339434300`, `is_hit=true`, `max_drawdown=0`, lesson `T+5 deterministic outcome review`.

GET detail and Chromium dashboard both displayed `hit` and `T+5 return 0.552% | max drawdown 0.000% | T+5 deterministic outcome review`. No stale pre-review placeholder remained.

## Browser QA

Chromium loaded `http://127.0.0.1:18082/` with HTTP 200. DOM checks for run ID, source reference, model, prompt, policy, hash, direct parent, and review were all `true`; page/network error list was empty.

## Product action implied by the finding

No product files were changed in this read-only audit. To fully refute H2, provider identity must become a first-class trusted lineage field, and the contract owner should decide whether canonical source/T+5 snapshot tables must carry self-contained evidence-grade provenance or whether linkage to `pipeline_runs.payload` is explicitly sufficient.
