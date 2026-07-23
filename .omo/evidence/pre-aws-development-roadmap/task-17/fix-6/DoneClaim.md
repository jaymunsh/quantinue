# Todo 17 Fix 6 DoneClaim

## Result

The public PostgreSQL production seam now has twelve explicit scenarios through
`build_job_runner` and `runner.tick`, plus two repository-level PostgreSQL
ownership auxiliaries. The combined matrix passed twice: `14 passed` in 12.75s
and `14 passed` in 12.11s.

## Public scenario map

1. Feature flag off: zero provider, usage, receipt, cooldown, signal, verdict,
   and order effects.
2. Strategist budget refusal: zero provider calls and released cooldown.
3. Happy hostile-input chain: strategist=1, critic=1, summary=0, usage=2,
   processed stage receipts=2, signal=1, verdict=1, cooldown=1, and
   orders/fills/plans=0.
4. Idle tick and reconstructed runner: no additional provider, usage, signal,
   verdict, or downstream write.
5. Critic budget refusal after strategist: strategist=1, critic=0; restart
   remains terminal and never rebills the processed strategist.
6. Malformed provider output: truthful persona failure, no signal/verdict/order.
7. Permanently hanging provider: bounded by 50ms stage timeout and retained as
   dispatched/uncertain, with no signal/verdict/order.
8. Pre-dispatch cancellation: usage=0 and cooldown released.
9. In-call cancellation: charged attempt and dispatched cooldown retained,
   with no signal/verdict/order and no silent zero-call claim.
10. Active wrong owner: provider=0 and `strategist_suppressed`.
11. Event completion then price trigger: t10 refused, restart t31 admitted.
12. Price completion then event trigger: t10 refused, restart t31 admitted.
13. Mixed tickers: AAPL success and malformed MSFT remain independently
   durable; per-tick outcome counters and latest successful result are retained;
   orders remain zero.

The hostile `external_data` scenario proves injected instructions stay inside
bounded model data while task, profile, persona, output contract, and zero-order
invariants remain controlled by trusted code.

## Direct SQL evidence

The happy-path public test queries the live PostgreSQL tables after the first
tick and asserts exactly `(2, 2, 1, 1, 1, 0, 0, 0)` for usage, processed
analysis-stage receipts with payloads, strategist signals, critic verdicts,
completed cooldowns, orders, fills, and order plans. It then performs an idle
tick and reconstructs `build_job_runner`; SQL remains usage=2, signal=1,
verdict=1 with correct event evidence/parent lineage and no extra provider call.

The refusal, malformed, hang, cancellation, wrong-owner, contention, and mixed
cases separately assert their truthful durable SQL states and expected zero or
charged deltas.

## Verification and hygiene

- PostgreSQL: task-owned `postgres:16-alpine` on 5490, fresh schema.
- Combined public/auxiliary matrix twice: 14/14 pass each run.
- Existing main public module alone: 11/11 pass.
- Separate trigger arbitration module: 3/3 pass in the combined runs.
- `git diff --check`: pass.
- Protected dirty `main.py` and `test_runtime_ownership.py` were not edited,
  staged, or overwritten by Fix 6.
- No `app/`, port 8020, or port 5445 access.

## Post-write review

The changed test surface owns one responsibility: adversarial public production
composition evidence. Untrusted provider/event data is parsed at existing typed
boundaries; no new production escape hatch, logger, or defensive layer was
introduced. The new arbitration module is 224 nonblank/noncomment lines.
