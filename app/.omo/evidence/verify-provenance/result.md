# Adversarial provenance verification

## Verdict

**AdversarialVerify: confirmed (freshness repair).** The original stale-write defect is fixed at the repository boundary. The PostgreSQL conflict predicate makes same-time and older replay inputs no-ops, while a strictly newer correction replaces the complete official-close/provenance tuple.

## Confirmed behavior

- `scripts/test_postgres_integration.sh -q tests/integration/test_provenance_postgres.py tests/integration/test_schema_sql.py` passed: **16 passed in 9.73s**. It used a disposable `quantinue-test-pg-*` container on a generated `55400-55499` port; cleanup left no matching container.
- `uv run pytest -q tests/unit/test_pipeline_evidence_trace.py tests/unit/test_review_processor.py tests/test_web.py` passed: **17 passed in 1.37s**.
- Targeted `ruff check`, `ruff format --check`, and `basedpyright` on the persistence/API paths passed (0 type errors/warnings).
- `RoleEvidenceTrace`, `EvidenceView`, `main.control_room_run`, and `dashboard.html` keep `model_provider` separate from `model_name`; the rendered dashboard has separate Korean “모델” and “제공자” fields. The real PostgreSQL regression selects and asserts both fields for raw disclosure/news, normalized disclosure/news signals, and T+5 snapshots.
- The DDL contains the required provenance columns on `tb_disclosure`, `tb_news`, `tb_disclosure_signal`, `tb_news_signal`, and `tb_review_price_snapshots`; source rows require provider while review snapshots intentionally allow no LLM lineage. The latter matches the deterministic role-11 processor.
- `save_source_records()` includes every requested provenance field in each conflict `set_` clause. The direct real-DB regression also confirmed exact `Decimal("0.97")` persistence and preserved parent arrays.

## Previous defect and repaired behavior

The original verification reproduced an unconditional stale overwrite. The repair changes `src/quantinue/db/reviews.py` to:

```python
where=table.c.captured_at < value.captured_at
```

I re-ran the production path in a separate disposable PostgreSQL 17 container on generated port `55500` (never `5432` or `5444`), after running the fixture pipeline. The real database results were:

```text
same captured_at + conflicting payload   -> original row retained
older captured_at + conflicting payload  -> original row retained
strictly newer captured_at               -> close, source_ref, evidence ID,
                                            parents, provider/model/prompt/policy/hash
                                            all atomically replaced by newer values
```

The equality policy is explicit first-writer-wins (`existing < incoming`, not `<=`), which is conservative for identical capture times and prevents a same-time replay from changing an official close. The focused real-PG regression now writes normal → newer correction → stale conflict and passed together with the schema suite: **17 passed in 10.24s**.

## Contract-test gap

The new `PROVENANCE_COLUMNS` catalog contract is wired through `Catalog.provenance_columns` and a real `information_schema.columns` query. `test_catalog_requires_auditable_provenance_columns` checks required names and nullability across raw disclosure/news, normalized signals, and T+5 snapshots. This closes the prior localization gap. It intentionally treats model lineage as nullable for deterministic T+5 captures, while raw/source signal provider identity is required.

## Scope and hygiene

- `docker ps -a` after both runs showed no `quantinue-test-pg-*`, `quantinue-adversarial-pg-*`, or schema test container. Existing user containers exposing or using `5432` were only observed, never changed; nothing listened on `5444` during this verification.
- The repository remains intentionally dirty/untracked at the app boundary (`git status --short` reports `M ../.gitignore` and `?? ./`); I made no product-code edit. This evidence file is the only verification artifact added.
