# Final F4 — scope-fidelity and safety-boundary audit

**Verdict: PASS (independent read-only audit, 2026-07-13).**

This audit inspected the current shared tree without starting, connecting to, binding,
or stopping PostgreSQL. It made no product-code changes and contains no credentials.

## Contract mapping

| Contract | Evidence | Verdict |
| --- | --- | --- |
| Rule 7: disclosure/news signals, strategist signals, and critic verdicts are append-only | Design §conv rule 7 (`docs/quantinue-integrated-design.html:348`) says signal/judgment rows must never be overwritten. `src/quantinue/db/domain_sources.py:35-153` uses `ON CONFLICT DO NOTHING` for raw disclosure/news and the two signal snapshots; `src/quantinue/db/domain.py:113-195` does the same for strategist signal and critic verdict, then reads the existing identifier. No update path targets these six tables. | PASS |
| Idempotent replay preserves first provenance | `tests/integration/test_append_only_postgres.py:60-341` writes an initial record, replays conflicting raw/signal/strategist/verdict values twice, and asserts all four provenance rows plus strategist/verdict rows equal their first persisted values. The asserted provenance set includes source reference, capture time, confidence, summary, evidence/parent IDs, provider/model, prompt/policy versions, and input hash. | PASS |
| MVP strategist vocabulary is only buy/hold; sell is phase 2 | The design explicitly declares `buy / hold` and defers `sell` to phase 2 (`docs/quantinue-integrated-design.html:343,361`). `src/quantinue/core/ontology.py:84-90` contains only `BUY` and `HOLD`; `db/schema.sql:85-98` enforces `CHECK (side IN ('buy','hold'))`. Unit regressions reject `Side('sell')` and a sell role output (`tests/unit/test_ontology.py:68-75`, `tests/unit/test_roles_05_08_contracts.py:56-69`). The disposable PostgreSQL regression expects an `IntegrityError` for `sell` (`tests/integration/test_domain_lifecycle_postgres.py:49-95`). | PASS |
| Paper-only order safety remains intact | Settings allow only the exact paper endpoint and default to mock/disabled (`src/quantinue/core/config.py:81-117`). The broker rechecks selected Alpaca mode, explicit enablement, and exact paper URL before submit (`src/quantinue/broker/alpaca.py:94-118`); its HTTP client always uses the paper base URL (`src/quantinue/broker/alpaca.py:235-240`). | PASS |
| No impact to a user’s localhost:5432; Compose uses host 5444 and internal db:5432 | `compose.yaml:11-12` publishes only `127.0.0.1:5444:5432`; its web service uses `db:5432` (`compose.yaml:21-30`). `scripts/test_compose_contract.sh:7-33` mechanically rejects host-port 5432 and `localhost:5432`. The disposable runner chooses only a free `55400-55499` port (`scripts/test_postgres_integration.sh:6-33`), never 5432 or 5444. | PASS |
| Updateable review snapshots were not converted to append-only | The design calls T+1..5 snapshots an idempotent upsert and specifies `updated_at` (`docs/quantinue-integrated-design.html:1451-1468`). `src/quantinue/db/reviews.py:114-153` retains its guarded snapshot conflict update; `db/schema.sql:129-141` retains `updated_at` for snapshots and final review. | PASS |

## Executed independent checks

```text
sh scripts/test_compose_contract.sh
  -> compose contract: PASS

uv run pytest -q tests/unit/test_ontology.py \
  tests/unit/test_roles_05_08_contracts.py \
  tests/unit/test_config.py tests/unit/test_broker_provider.py
  -> 87 passed in 0.88s

git diff --check
  -> no whitespace errors
```

The actual PostgreSQL checks are deliberately exercised by
`scripts/test_postgres_integration.sh` in the parent final-gate run. This F4 audit did
not run that script because the delegated brief explicitly requires no Docker/database
activity; it verified that the runner is disposable and isolated and that the real
PostgreSQL regression tests are present and correctly target the contract.

## Scope and residual risk

- `tb_fill.side` intentionally still includes `sell` (`db/schema.sql:124-127`): it records
  a fill event, not the MVP strategist/action vocabulary. That does not broaden the
  strategist contract, and the paper broker's order payload remains fixed to buy.
- Existing `ON CONFLICT DO UPDATE` paths remain only on explicitly mutable records such
  as daily observations, accounts/orders, and reviewer snapshot/final-review state.
  They are outside design rule 7; no broad rewrite was made.
- This is an evidence/scope audit, not a replacement for the parent’s full static,
  disposable-PostgreSQL, Docker/API, and responsive-operation-room gates.
