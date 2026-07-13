# H3 reproduction commands

Database URL used by pytest:

`postgresql+asyncpg://quantinue:quantinue@127.0.0.1:55443/quantinue_h3`

Initial red run:

```sh
QUANTINUE_TEST_DATABASE_URL="$URL" uv run pytest -q \
  tests/integration/test_domain_lifecycle_postgres.py \
  tests/integration/test_persistence_postgres.py::test_postgres_daily_order_cap_is_cross_process_atomic
```

Relevant output:

```text
ForeignKeyViolationError: insert or update on table "tb_technical" violates foreign key constraint "tb_technical_trade_date_ticker_fkey"
DETAIL: Key (trade_date, ticker)=(2026-07-02, NVDA) is not present in table "tb_daily_pick".
1 failed, 1 passed in 2.54s
```

FK toggle run in separate `quantinue_h3_toggle` database:

```sql
ALTER TABLE tb_technical DROP CONSTRAINT tb_technical_trade_date_ticker_fkey;
```

```text
1 passed in 2.30s
```

Fresh-current validation with the FK retained:

```text
3 passed in 2.92s
```

T+5 ASGI API replay:

```text
REVIEW 200 {'signal_id': 1, 'status': 'completed', 'captured_offsets': [1, 2, 3, 4, 5]}
RUN 200 {'status': 'completed', 'progress': 11, 'review': {'outcome': 'miss', 'summary': 'T+5 return -16.667% | max drawdown -19.782% | T+5 deterministic outcome review'}}
```

Catalog query proved the runtime FK exists:

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='tb_technical'::regclass AND contype='f';
```

```text
tb_technical_trade_date_ticker_fkey | FOREIGN KEY (trade_date, ticker) REFERENCES tb_daily_pick(trade_date, ticker)
```
