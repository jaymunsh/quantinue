# G2 runtime debug audit

**Verdict: PASS.** All three required hypotheses were tested against actual runtime behavior and refuted.

| Hypothesis | Runtime evidence | Result |
| --- | --- | --- |
| H1: conflicting replay overwrites append-only raw/provenance/model fields | Disposable PostgreSQL integration runner passed all 19 tests, including the adversarial conflicting-ledger replay test. | PASS: first persisted values were retained. |
| H2: strategist `sell` crosses model or PostgreSQL boundary | The same disposable runner passed the real schema sell-rejection regression; the final full unit gate covers model rejection. | PASS: `sell` is rejected at both boundaries. |
| H3: cleanup regressed retry/terminal classification | Asyncio-debug minimal pipeline and retry suite: `28 passed`; direct classifier driver returned transient retryable, HTTP 400 terminal, and authentication terminal decisions. | PASS: transient retry and terminal failure separation remains intact. |

## Commands and observed results

```text
sh scripts/test_postgres_integration.sh -q
19 passed in 9.48s

PYTHONASYNCIODEBUG=1 uv run pytest -q tests/unit/test_pipeline_resilience.py tests/unit/test_retry.py
28 passed in 0.36s
```

The direct minimal runtime classification emitted redacted stable codes only:
`TRANSIENT_FAILURE` retryable, `HTTP_FAILURE` terminal for HTTP 400, and
`AUTHENTICATION_FAILURE` terminal.

## Isolation and cleanup

PostgreSQL execution used only the script-owned disposable runner. No host
`localhost:5432` resource was inspected, used, stopped, or changed; no secret,
connection URL, dynamic port, or container identifier is recorded. The runner
completed successfully and its scoped cleanup trap owned its temporary resource.
No debug instrumentation or temporary runtime artifact remains.
