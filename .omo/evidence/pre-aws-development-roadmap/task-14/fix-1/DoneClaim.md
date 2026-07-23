# Todo 14 fix-1 DoneClaim

Fix-forward closes every finding in `AdversarialVerify.md`.

- Production runtime: `JobRunner.tick()` dispatches `EventIngestionRuntime`; `job_factory`
  binds the existing SEC, Alpaca news, and wire providers to the transactional repository.
- Compressed clock: 31 minute ticks observe SEC 2 calls, news 3, wire 4, proving exact
  30/15/10 minute boundaries without duplicate dispatch.
- SEC restart: the adapter exposes each date from cursor-overlap through now as a separate
  page. A failure can only leave the cursor at the last committed date, and restart refetches
  overlap before continuing.
- Monotonic cursor: the PostgreSQL upsert updates only when the incoming comparable ISO
  checkpoint is greater. Sequential reordered and concurrent commits both retain 12:03 over
  12:01.
- Configuration typing: canonical YAML is parsed through a typed `JsonValue` boundary;
  scoped basedpyright including `policy.py` reports zero errors.

Verification:

- Focused suite twice: `13 passed` each; concurrent direct probe separately passed.
- Ruff: pass.
- basedpyright event/config changed scope: zero errors (final warning cleanup applied).
- compileall, diff check, secret scan: pass.
- Direct PostgreSQL: `wire:2026-07-24T12:03:00+00:00`, `documents=2`.
- Existing duplicate, late, loop, partial failure, malformed, cancellation, restart, and
  prompt-injection probes remain green.
- Cleanup: disposable PostgreSQL removed; 5490/8021 free; protected 8020 PID and 5445
  listener unchanged; protected dirty file hashes unchanged.

Residual risk: provider timestamps are canonical ISO-8601 strings, so lexical ordering is
the explicit cursor comparison contract.
