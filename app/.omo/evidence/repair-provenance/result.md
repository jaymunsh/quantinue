# Provenance repair evidence

## Scope

- Kept `model_provider` separate from `model_name` in LLM metadata and carried both, plus prompt/policy/input-hash lineage, into raw disclosure/news ledgers and their normalized signal snapshots.
- Kept T+5 source reference, observation/capture times, confidence, evidence ID, parent IDs, and optional model lineage through the PostgreSQL upsert path.
- Replaced a concurrent malformed source upsert with atomic, non-lossy conflict updates. Confidence is serialized through `Decimal(str(value))` so PostgreSQL `NUMERIC` does not retain binary-float artifacts.

## Verification

```text
uv run ruff check <touched files>                         PASS
uv run ruff format --check <touched files>                PASS
uv run basedpyright <touched files>                       0 errors, 0 warnings
scripts/test_postgres_integration.sh -q \
  tests/integration/test_provenance_postgres.py \
  tests/integration/test_schema_sql.py                    16 passed
uv run pytest -q tests/unit/test_pipeline_evidence_trace.py \
  tests/unit/test_review_processor.py tests/test_web.py   17 passed
```

`test_provenance_postgres.py` runs the complete fixture pipeline against a disposable PostgreSQL container and asserts the raw ledger, normalized signal snapshot, and T+5 snapshot values directly.

## Cleanup receipt

The PostgreSQL script selected a free port in `55400-55499`, never used `5432` or `5444`, and its UUID-named `quantinue-test-pg-*` container was removed by its trap. No matching container remained after verification.

## Freshness repair

- `PostgresReviewRepository.save_snapshot` now uses `ON CONFLICT ... DO UPDATE ... WHERE existing.captured_at < incoming.captured_at`.
- The real PostgreSQL regression first writes a normal snapshot, then a newer corrected snapshot, then a stale conflicting snapshot with different close, source, evidence, parent IDs, and LLM metadata. The final row remains the newer one.
- The schema catalog fixture now asserts the provenance-column names and nullability for raw disclosure/news, normalized signal snapshots, and T+5 snapshots. Confidence and T+5 source CHECK constraints remain exact-catalog assertions.

Focused rerun after the repair: format/check PASS; basedpyright `0 errors`; disposable PostgreSQL `17 passed`; unit/control-room slice `17 passed`.
