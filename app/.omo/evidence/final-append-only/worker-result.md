# Append-only ledger verification

## Result

The six immutable tables now insert only on first observation and reuse their
canonical identifier on a conflict:

- `tb_disclosure`, `tb_news`, `tb_disclosure_signal`, `tb_news_signal`
- `tb_strategist_signals`, `tb_critic_verdict`

`tb_review_price_snapshots` was not changed; its freshness-aware update path
remains updateable by design.

## Fail-first proof

Before the repository change, the disposable PostgreSQL test wrote an initial
`LEDGERX` source/signal/verdict set and replayed a conflicting payload twice.
The assertion failed because `tb_disclosure` changed from its first fixture
source/provenance/model values to the conflicting values. This reproduced the
reported mutation defect rather than a setup failure.

## Passing commands

```text
sh scripts/test_postgres_integration.sh -q \
  tests/integration/test_provenance_postgres.py::test_postgres_preserves_model_and_source_lineage_in_normalized_records
17 passed

uv run ruff format --check src/quantinue/db/domain_sources.py \
  src/quantinue/db/domain.py tests/integration/test_append_only_postgres.py \
  tests/integration/test_provenance_postgres.py
4 files already formatted

uv run ruff check src/quantinue/db/domain_sources.py \
  src/quantinue/db/domain.py tests/integration/test_append_only_postgres.py \
  tests/integration/test_provenance_postgres.py
All checks passed

uv run basedpyright src/quantinue/db/domain_sources.py \
  src/quantinue/db/domain.py tests/integration/test_append_only_postgres.py \
  tests/integration/test_provenance_postgres.py
0 errors, 0 warnings, 0 notes

sh -x scripts/test_postgres_integration.sh -q \
  tests/integration/test_append_only_postgres.py
19 passed
```

## Manual data-surface observation

The real PostgreSQL test reads the four source rows plus strategist and critic
rows before and after two conflicting replays. The complete typed projections
are equal after the replay: source reference, capture time, confidence,
summary, evidence ID, parent evidence IDs, provider, model name, prompt and
policy versions, input hash, strategist side/conviction/summary/evidence, and
all critic fields retain the first-write values. `save_signal` and
`save_verdict` also return the original identifiers on both replays.

## Adversarial probes and cleanup

- Retry/replay: the same conflicting payload ran twice with unchanged rows and
  stable identifiers.
- Stale state: the test uses unique `LEDGERX` / 2032 identities, so it cannot
  inherit the shared fixture keys used by older integration tests.
- Dirty tree: relevant paths were already untracked within the shared app
  worktree; no reset, checkout, deletion of existing files, or unrelated edit
  was performed.
- Misleading success: the assertion compares real PostgreSQL rows, not SQL
  statement completion or mock calls.
- Cleanup: the disposable runner selected a free port in `55400-55499` and
  removed its uniquely named PostgreSQL container through its trap. No
  connection, bind, inspection, stop, or modification involved ports 5432 or
  5444.
