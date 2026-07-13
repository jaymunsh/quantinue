# Independent strategist sell-contract verifier result

## Scope and independence

Read-only verification of the current workspace and worker evidence
`worker-result.md`. No application, schema, test, Docker, or configuration files
were changed by this verifier. This evidence file is the sole verifier artifact.

## Commands and observed results

```text
uv run pytest -q tests/unit/test_ontology.py tests/unit/test_roles_05_08_contracts.py tests/unit/test_config.py tests/unit/test_broker_provider.py -k 'strategist_side_rejects_phase_two_sell or strategy_output_model_rejects_phase_two_sell or alpaca_url_accepts_only_the_exact_paper_endpoint or trading_enabled_requires_selected_alpaca_mode or refuses_non_paper_endpoint'
7 passed, 80 deselected in 1.08s

sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py -k 'postgres_rejects_phase_two_sell_strategist_signal'
1 passed, 18 deselected in 1.44s

uv run pytest -q tests/integration/test_schema_sql.py
5 passed in 2.25s
```

The PostgreSQL command used only `scripts/test_postgres_integration.sh`. Its
implementation chooses an ephemeral loopback port in 55400--55499, mounts the
current `db/schema.sql` read-only, and tears down only its UUID/timestamp-named
test container through its EXIT trap. This verifier did not inspect, bind, use,
or stop ports 5432 or 5444.

## Contract findings

- `src/quantinue/core/ontology.py`: `Side` contains exactly `buy` and `hold`;
  `Side("sell")` is rejected. The corresponding Pydantic
  `StrategyOutput.side: Literal["buy", "hold"]` negative test passed.
- `db/schema.sql`: `tb_strategist_signals.side` has actual PostgreSQL CHECK
  `side IN ('buy','hold')`. The disposable database test inserted required
  parents and observed `IntegrityError` for `side='sell'`; this is not merely a
  textual schema assertion.
- `tb_fill.side` remains intentionally separate with CHECK
  `side IN ('buy','sell')`; schema-contract tests passed and the source contains
  no strategist expansion back to sell. This preserves settlement/fill
  vocabulary while strategist action remains MVP-only.
- Paper-only execution safety remains present: `Settings` accepts only
  `https://paper-api.alpaca.markets`, rejects enabled trading without the Alpaca
  mode/credentials, and the focused safety tests passed. Role 10 still produces
  a buy bracket (`stop < entry < take-profit`).

## Stale, dirty, and misleading-success checks

- Worker evidence claims the same contract; this verifier reran the named unit,
  real-PostgreSQL, and schema tests independently rather than accepting that
  claim.
- `git diff --check` returned success. `git status --short` reports the parent
  `.gitignore` modified and the entire current app directory as untracked
  (`?? ./`), so Git cannot attribute individual app-file edits or provide a
  meaningful local diff baseline. No such file was altered here.
- Searches found no `Side.SELL` and no strategist three-value side CHECK. The
  two intended DDL constraints are present exactly as above.

## Cleanup receipt

After the disposable PostgreSQL test, `docker ps --filter
'name=quantinue-test-pg-' --format '{{.Names}}'` returned empty output. No
test-runner container remained.

## Verdict

**PASS, high confidence.** The current MVP strategist/action model and actual
PostgreSQL schema reject sell, while `tb_fill` retains buy/sell and paper-only
execution protections remain intact. Residual confidence limitation: the app
directory's untracked Git state prevents historical-diff attribution, not
runtime contract verification.
