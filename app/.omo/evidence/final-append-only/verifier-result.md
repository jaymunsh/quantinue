# Independent append-only ledger verifier result

## Verdict

**APPROVED** (confidence: 0.98).

The current implementation keeps all six required ledger tables immutable on
key conflict and reuses the existing strategist and critic identifiers. The
actual disposable PostgreSQL integration suite passed with the adversarial
replay test present. The refreshable review snapshot path remains intentionally
updateable when, and only when, a newer capture timestamp is supplied.

## Baseline and scope safety

- Repository baseline was already dirty/untracked from other work; this review
  made no source-code changes and did not reset, checkout, clean, or delete
  existing work.
- No host database ports were inspected, bound, queried, stopped, or otherwise
  modified. PostgreSQL execution used only the project disposable runner.
- The runner selects an isolated loopback test port in its private high range,
  starts a timestamp-named disposable container, and has an exit trap that
  removes that named container. No credential, URL, port number, or container
  identifier is recorded here.

## Implementation inspection

| Table | Conflict key | Observed behavior |
| --- | --- | --- |
| `tb_disclosure` | `filing_no` | `ON CONFLICT DO NOTHING` |
| `tb_news` | `news_key, ticker` | `ON CONFLICT DO NOTHING`; existing `id` is selected for the dependent signal |
| `tb_disclosure_signal` | `ticker, cycle_ts` | `ON CONFLICT DO NOTHING` |
| `tb_news_signal` | `ticker, cycle_ts` | `ON CONFLICT DO NOTHING` |
| `tb_strategist_signals` | `ticker, cycle_ts, inv_type` | `ON CONFLICT DO NOTHING`; canonical `id` is selected and returned |
| `tb_critic_verdict` | `signal_id` | `ON CONFLICT DO NOTHING`; canonical `id` is selected and returned |

The immutable paths are in `src/quantinue/db/domain_sources.py` and
`src/quantinue/db/domain.py`. None writes a conflict-update assignment for the
six tables. The only reviewed `DO UPDATE` relevant to this boundary is
`PostgresReviewRepository.save_snapshot`, which deliberately accepts a newer
`captured_at` and rejects same/older captures via its `WHERE` predicate.

## Runtime evidence

Commands run from the repository root:

```text
sh scripts/test_postgres_integration.sh -q
19 passed in 9.42s

uv run ruff format --check src/quantinue/db/domain.py src/quantinue/db/domain_sources.py tests/integration/test_append_only_postgres.py tests/integration/test_provenance_postgres.py
4 files already formatted

uv run ruff check src/quantinue/db/domain.py src/quantinue/db/domain_sources.py tests/integration/test_append_only_postgres.py tests/integration/test_provenance_postgres.py
All checks passed!
```

`tests/integration/test_append_only_postgres.py` writes initial records,
replays a deliberately conflicting source/signal/verdict payload twice, and
asserts that all four source rows preserve source reference, timestamps,
confidence, summary, evidence, parent evidence, provider/model, prompt,
policy, and input hash. It also asserts that strategist and critic replays
return their original identifiers and retain their original decision fields.
The second identical conflicting replay establishes idempotence of a replay.

`tests/integration/test_provenance_postgres.py` independently writes a newer
review snapshot followed by an older one, then reads back the newer row. This
confirms that the R1 change did not freeze the design-authorized freshness
update path.

## Adversarial audit

1. **Update-path hypothesis:** a legacy `DO UPDATE` might still overwrite raw
   or provenance fields. Refuted by direct conflict-path inspection and the
   conflicting PostgreSQL replay preserving every selected provenance/model
   field.
2. **Identifier hypothesis:** `DO NOTHING` might make callers lose the
   canonical decision identifiers. Refuted by the real test: conflicting
   strategist and critic replays return the original ids.
3. **Over-correction hypothesis:** append-only enforcement might accidentally
   disable review snapshot correction. Refuted by the isolated PostgreSQL
   provenance test's newer-then-stale read-back behavior and the explicit
   timestamp-qualified `DO UPDATE` implementation.

No broad exception swallowing was found in the reviewed persistence paths.

## Cleanup receipt

The disposable runner exited successfully. Its shell exit trap is responsible
for removal of its uniquely named database container; no persistent server,
browser, listener, temporary script, or debug instrumentation was created by
this verifier. The pre-existing dirty/untracked workspace was left intact.

## Limits

The worker's historical fail-first assertion was read but not independently
reproduced because the old mutating implementation is no longer present; the
current-state runtime proof is the passing adversarial replay. This is not a
current correctness gap.
