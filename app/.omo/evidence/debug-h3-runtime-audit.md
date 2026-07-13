# H3 domain lifecycle runtime audit

Date: 2026-07-13 Asia/Seoul
Isolation: disposable PostgreSQL 17 container `quantinue-debug-h3-20260713`, host `127.0.0.1:55443`; no named volume and no access to localhost:5432/5444.

## Hypotheses and verdicts

1. **Stage/FK order inconsistency: confirmed in the initially observed runtime.**
   - Initial integration exit: `1 failed, 1 passed`.
   - Exact exception: `ForeignKeyViolationError`, constraint `tb_technical_trade_date_ticker_fkey`, key `(trade_date, ticker)=(2026-07-02, NVDA)` absent from `tb_daily_pick`.
   - Exact partial state: `pipeline_runs.status=running`; attempts were `01/completed`, `02/running`; checkpoints contained only `01`; `tb_universe=2`, `tb_daily_pick=1`, `tb_technical=0` (the extra universe/pick rows belonged to the independent cap fixture).
   - Catalog verified the allegedly missing FK was actually present: `FOREIGN KEY (trade_date, ticker) REFERENCES tb_daily_pick(trade_date, ticker)`. Total domain FKs returned: 19.
   - Toggle proof: in a separate disposable database, dropping only `tb_technical_trade_date_ticker_fkey` changed the same lifecycle test to `1 passed in 2.30s`.
   - While this audit was running, shared product files changed: stage 02 no longer writes technical rows, and stage 03 now atomically writes daily picks then selected technical children through `save_daily_stage`. A fresh database retaining the FK then passed the lifecycle + concurrent-cap selection: `3 passed in 2.92s`.

2. **Daily order cap race/duplicate: refuted for the tested two-process cap=1 case.**
   - Real PostgreSQL test assertion observed exactly `sorted(outcomes) == [False, True]` and passed.
   - Read-back for generated ticker `C38A122E0`: `signal_count=2`, `order_count=1`, status `planned`.
   - Independent NVDA lifecycle row: `signal_count=1`, `order_count=1`, status `filled`.
   - Replaying the same NVDA cycle left canonical signal/order/fill counts at `1/1/1`.

3. **T+5 payload/FK inconsistency: refuted on a completed canonical run.**
   - API replay: HTTP 200 `{'signal_id': 1, 'status': 'completed', 'captured_offsets': [1, 2, 3, 4, 5]}`.
   - Run API: HTTP 200, `status=completed`, `progress=11`, review outcome `miss`, summary `T+5 return -16.667% | max drawdown -19.782% | T+5 deterministic outcome review`.
   - Snapshot rows: offsets 1..5, dates `2026-07-06` through `2026-07-10`, closes `103,104,105,106,107`, source `market_data`.
   - Review read-back: `ret_1d=-19.78193146417445482866043614`, `ret_3d=-18.22429906542056074766355140`, `ret_5d=-16.66666666666666666666666667`, `is_hit=false`, `max_drawdown=-19.78193146417445482866043614`.
   - Orphan counts were all zero: daily pick, technical, order, fill, review = `0,0,0,0,0`.

## Residual confirmed defect

Resuming the initially interrupted cycle after the shared fix completed the run, but did not reconcile the old running attempt. Exact state:

- `pipeline_runs.status=completed`
- stage 02 attempt 1: `running`, `finished_at=NULL`
- stage 02 attempt 2: `completed`
- stages 01 and 03..11: one completed attempt each
- total attempts: 12 for 11 components; checkpoints: exactly 11

Thus canonical domain data is consistent after the current stage-order fix, but execution history can remain internally inconsistent after an exception escapes between `start_attempt` and failure persistence.

## Fresh-current exact counts

After current code, identical-cycle replay, T+5 processing, and one cap-race fixture:

| table | count |
|---|---:|
| pipeline_runs | 1 |
| pipeline_stage_attempts | 11 |
| pipeline_checkpoints | 11 |
| tb_universe | 2 |
| tb_daily_pick | 2 |
| tb_technical | 1 |
| tb_macro | 1 |
| tb_disclosure / tb_disclosure_signal | 1 / 1 |
| tb_news / tb_news_signal | 1 / 1 |
| tb_strategist_signals | 3 |
| tb_critic_verdict | 1 |
| tb_account | 2 |
| tb_order | 2 |
| tb_fill | 1 |
| tb_review_price_snapshots | 5 |
| tb_review | 1 |

The second account, two extra signals, and second order are the isolated cap=1 fixture, not duplicate NVDA lifecycle writes.
