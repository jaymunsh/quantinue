# Global QA lane

## Verdict

`FAIL` (verification infrastructure blocked; this is not a demonstrated product defect).

## Scope and safety

- No command reached a project process: every attempted terminal invocation, including `true`, failed before launch with `Too many open files (os error 24)`.
- Consequently this lane did not run Docker, PostgreSQL, compose, or inspect/use host ports `5432`/`5444`.
- No source files, containers, volumes, networks, databases, secrets, or user data were changed.

## Required command reruns

| Required check | Outcome |
| --- | --- |
| `uv run ruff format --check .` | Not started: terminal process creation blocked by `EMFILE`. |
| `uv run ruff check .` | Not started: terminal process creation blocked by `EMFILE`. |
| `uv run basedpyright` | Not started: terminal process creation blocked by `EMFILE`. |
| `uv run pytest -q` | Not started: terminal process creation blocked by `EMFILE`. |
| `sh scripts/test_postgres_integration.sh -q` | Not started: terminal process creation blocked by `EMFILE`; no DB port was touched. |
| `sh scripts/test_compose_contract.sh` | Not started: terminal process creation blocked by `EMFILE`. |

## User-facing scenario evidence (fresh independent F3 lane)

I inspected the completed F3 lane status supplied in this shared team run. Its isolated Compose QA used host `5444` mapped to Docker `db:5432`, selected an F3-only web port `18011` to avoid an existing collision, and removed all temporary containers, image, volume, network, payloads, and journals afterwards. It reports:

1. Mock API happy path completed all 11 stages with 11 evidence records, a `buy` decision, a filled paper order, and a pending T+5 review.
2. Chromium form submission and dashboard checks passed at widths 1440, 1024, 768, and 390, with no console errors, clipping, or horizontal overflow.
3. A disposable timeout scenario rendered `FAILED`, `timed_out`, and `ROLE_TIMEOUT`, retained the checkpoint, and did not render raw payload.
4. Two independent visual passes marked the responsive UI pass, including natural, unclipped Korean text and safe timeout redaction.

This supports the manual-surface behavior but is not a substitute for this lane's mandated reruns.

## Blocker

Global OS file-descriptor exhaustion (`EMFILE`) prevented launching any shell process. Re-run the six required commands once process creation succeeds, while keeping the PostgreSQL runner as the sole database path.
