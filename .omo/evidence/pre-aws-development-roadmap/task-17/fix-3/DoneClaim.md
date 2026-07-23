# Fix 3 done claim

Implemented the diagnosed owner-token state machine and durable LLM budget
admission:

- every receipt mutation acknowledges exactly one owner generation;
- stale reclaim is limited to un-dispatched claims after an ownership TTL;
- strategist cooldown completes only with the durable stage payload;
- intraday failure/refusal releases cooldown ownership and success completes it;
- WatchRunner no longer maintains an independent cooldown authority;
- PostgreSQL atomically admits committed usage plus live maximum reservations,
  owner-fences dispatch/release/settlement, and writes settlement plus usage in
  one transaction;
- model input bounds untrusted `external_data` to 32,768 characters.

Command-complete evidence:

- PostgreSQL 16 fresh schema: passed.
- Predecessor migration applied twice: passed.
- Real PostgreSQL schema/event/ownership/budget matrix: `27 passed`, repeated
  twice.
- Owner and two-connection budget critical module: repeated 10 times.
- Full unit suite: `719 passed`, repeated twice.
- Exact Fix2 14-file basedpyright surface: baseline `420 errors, 8 warnings`;
  candidate `420 errors, 8 warnings`; delta `0 errors, 0 warnings`.
- Ruff, compileall, and diff check: passed.
- Direct PostgreSQL receipt: reservation `settled|1|0.75`, usage
  `1|0.50`, orders `0`.

Cleanup preserves the foreign `main.py` and `test_runtime_ownership.py` hashes
recorded by the diagnosis.
