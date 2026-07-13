# F4 scope-fidelity and security-boundary audit

**Result: FAIL (one MVP-scope discrepancy).**

## Scope discrepancy

The authoritative design's MVP boundary limits strategist `side` to `buy / hold` and
explicitly defers `sell` to phase 2 (`../docs/quantinue-integrated-design.html`, lines
361, 654, 658, 1220, and 1718).  Although the executable role-07 contract correctly
limits its public output to `Literal["buy", "hold"]`, the persisted ontology and schema
still admit the deferred value:

- `src/quantinue/core/ontology.py`: `Side.SELL = "sell"`.
- `db/schema.sql:89`: `tb_strategist_signals.side CHECK (side IN ('buy','hold','sell'))`.

This does not currently create an active sell order: `OrderPlan` has no side field and
`AlpacaBroker._payload()` fixes `"side": "buy"`.  It is nevertheless a DB/ontology
contract that permits phase-2 active-sell state, so F4 cannot pass until the canonical
allowed values are narrowed to `buy / hold` (or the original design is explicitly revised).

## Passing safety boundaries

- Compose publishes only `127.0.0.1:5444:5432` for Postgres and uses `db:5432` internally.
  `sh scripts/test_compose_contract.sh` passed.  The disposable integration runner binds
  only a free `127.0.0.1:55400-55499` port and does not select `5432` or `5444`.
- `Settings` accepts exactly `https://paper-api.alpaca.markets`; `AlpacaBroker` rechecks
  selected+enabled+exact-paper URL before requests and its client base URL is the paper
  constant.  Targeted `test_config.py` and `test_broker_provider.py` passed (29 tests).
- Defaults are memory/fixture/mock with `trading_enabled=false` and broker mock.  Alpaca
  needs selected credentials plus `trading_enabled=true`; OpenAI requires its key only
  when selected.
- Real provider tests are marked `real_key` and collection-skipped unless
  `QUANTINUE_RUN_REAL_KEY_TESTS=1`.  The state-changing Alpaca order additionally requires
  `QUANTINUE_RUN_ALPACA_ORDER_TEST=1` and `QUANTINUE_TEST_DATABASE_URL`.
- `.env.example` contains empty real-provider key values plus local LLM instructions;
  parent `.gitignore` ignores `app/.env` and variants. `scripts/scan_secrets.sh` passed.
- Single-account, fixed buy bracket, integer quantity behaviour is enforced.  No
  `partially_filled` state or trailing-order payload is implemented; multi-account is
  documented as phase 2.
- Provenance fields include source reference, capture time, confidence, evidence id,
  direct parents, model provider/name/prompt/policy/input hash in the canonical SQL schema;
  `tests/integration/test_provenance_postgres.py` asserts their lossless persistence.

## Commands run

```text
sh scripts/test_compose_contract.sh  -> compose contract: PASS
uv run pytest tests/unit/test_config.py tests/unit/test_broker_provider.py -q
                               -> 29 passed in 0.12s
./scripts/scan_secrets.sh       -> No provider-token or private-key patterns detected.
```

No database container was started, queried, stopped, or modified by this audit.
