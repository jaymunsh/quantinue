# H1 transport retry runtime audit — FAIL

Verdict: **H1 confirmed for PostgreSQL failed-run resume.** PASS is not allowed.

`ConnectError`, `ReadError`, and `RemoteProtocolError` do not bypass in-budget retry. Memory and disposable PostgreSQL runs each produced `retrying -> completed`, stable `TRANSPORT_FAILURE`, redacted `provider transport failed`, and zero remaining `running` attempts.

Exhaustion also closes and redacts its attempt. Memory resume succeeds on the same run ID. PostgreSQL resume fails: `finish_run()` replaces `pipeline_runs.payload` with public `PipelineRun`, while `claim()` decodes resumable failed payload as internal `PipelineContext`. Runtime raises `PipelineContext.request Field required` at `src/quantinue/db/postgres.py:114` before the next attempt starts.

Toggle evidence: the adapter rejects `PipelineRun` payload with `('request',) missing`, while `encode_context(PipelineContext)` parses with the same run ID. Verbatim commands/output are in `debug-h1-runtime.txt`.

No product files changed. PostgreSQL evidence used a disposable container on a dynamic 55520-55579 port; the EXIT trap removed it. Existing compose services and ports 5432/5444 were not modified.
