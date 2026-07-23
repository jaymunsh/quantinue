# DoneClaim: Todo 14

## Claim

SEC, Alpaca news, and wire sources now share a typed incremental event boundary. Stable
provider IDs and deterministic SHA-256 content hashes feed the immutable Todo 13 ledger.
Each complete page writes document/version/event/ingestion receipt and advances its cursor
inside one PostgreSQL transaction. Duplicate, reordered, late, restarted, failed,
cancelled, malformed, and repeated-token inputs cannot skip a checkpoint.

## TDD evidence

- Baseline/PIN: existing providers return stable SEC accession numbers, Alpaca numeric IDs,
  and deterministic wire GUID hashes; `red.txt` captures the missing config and ingestion
  boundary before production code.
- RED: import/collection failed for `EventIngestionConfig` and `quantinue.events`.
- GREEN: focused unit and real PostgreSQL integration suite: `10 passed`; repeated twice.
- Cadences/overlap: SEC 30/60 minutes, news 15/30, wire 10/20, owned by
  `config/pipeline.yaml` and parsed by strict Pydantic config.

## Verification

- Scoped Ruff: pass.
- basedpyright for new event production/tests: `0 errors, 0 warnings`.
- compileall: pass.
- canonical YAML load/assertion: pass.
- `git diff --check`: pass.
- secret scan: clean.
- Manual PostgreSQL SQL counts/cursors: see `manual-qa.md` and `manual-output.txt`.

## Adversarial matrix

- Duplicate IDs/content: one immutable document/version/event/receipt.
- Reordered and late overlap: persisted once without cursor regression.
- Partial/network failure: last complete page remains durable; failed page does not advance.
- Repeated token: detected before repeated page transaction.
- Restart: resumes from durable cursor without skip.
- Malformed provider item: constraint error rolls back page and cursor.
- Prompt injection/paywall text: data only; no URL follow or instruction execution.
- Cancellation: prior checkpoint/rows preserved.
- Long command/network bounds: provider clients retain explicit timeouts; verification
  commands were bounded and no external article request was made.
- Misleading success: direct SQL verified document/version/event/receipt counts and cursors.

## Cleanup and residual risk

Cleanup proof is recorded after the disposable container is removed. No Todo 13 schema
field was added. The adapters intentionally inherit provider batch granularity; provider
HTTP pagination remains inside the existing Alpaca client while the durable boundary
commits its returned complete batch.
