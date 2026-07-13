# Task 1 — bounded terminal administrator-detail contract

## Delivered

- Added frozen, strict `TerminalRunDetail` records for disclosure/news collection facts,
  strategy facts, and critic facts. All display fields are bounded; unknown raw-payload
  fields are forbidden.
- Added `PipelineRun.detail` with a `default_factory`, so legacy, partial, failed, and
  blocked terminal runs deserialize to explicit empty placeholders.
- Moved the existing `OrderResult` and `ReviewResult` boundary models into a focused
  terminal-run module while preserving imports from `quantinue.core.contracts`.

## TDD evidence

1. Characterization first: `uv run pytest tests/unit/test_terminal_detail_contract.py -q`
   passed with the existing terminal JSON round-trip (`1 passed`).
2. Red test next: importing the new contract records failed with
   `ImportError: cannot import name 'CollectionFact'`, before implementation.
3. Green test set: `uv run pytest tests/unit/test_terminal_detail_contract.py
   tests/unit/test_pipeline_evidence_trace.py -q` → `10 passed`.

## Verification

```text
uv run ruff format --check src/quantinue/core/contracts.py \
  src/quantinue/core/terminal_detail.py \
  src/quantinue/core/terminal_run_types.py \
  tests/unit/test_terminal_detail_contract.py
4 files already formatted

uv run ruff check <same paths>
All checks passed!

uv run basedpyright <same paths>
0 errors, 0 warnings, 0 notes
```

Pure-LOC scan:

```text
src/quantinue/core/contracts.py          236
src/quantinue/core/terminal_detail.py     36
src/quantinue/core/terminal_run_types.py  18
```

## Manual runtime proof

Executed a minimal `uv run python` driver that serialized a completed run and parsed a
legacy failed run. Its redacted output retained only display-safe fields:

```json
{"detail":{"disclosure":{"title":"10-Q filed","summary":"Revenue growth","source":"SEC EDGAR","reference":"sec://filing/0001","score":0.8},"news":{"title":"","summary":"","source":"","reference":"","score":null},"strategy":{"proposal":"","rationale":"","gate":"","blockers":[]},"critic":{"verdict":"","rationale":"","layer":""}}}
{"disclosure":{"title":"","summary":"","source":"","reference":"","score":null},"news":{"title":"","summary":"","source":"","reference":"","score":null},"strategy":{"proposal":"","rationale":"","gate":"","blockers":[]},"critic":{"verdict":"","rationale":"","layer":""}}
```

No external service, Docker resource, database, or environment file was accessed; no
runtime cleanup was needed.

## Adversarial probes

- Malformed input: applicable. A detail containing an unknown `raw_provider_payload`
  and an oversized title is rejected by the strict bounded model test.
- Stale state / legacy parse: applicable. A legacy terminal JSON payload without
  `detail` yields the four explicit empty detail placeholders.
- Dirty worktree: applicable. The pre-existing dirty/untracked workspace was retained;
  no reset, checkout, deletion, or unrelated edit was performed.
- Misleading success output: applicable. A combined verification command lost its PATH
  after the type-check command, so its incomplete follow-on output was discarded and
  pure-LOC and manual checks were rerun as isolated commands.
- Role capture, API projection, templates, CSS, scheduler, browser, and PostgreSQL
  persistence are not applicable to this bounded contract task; they remain later plan
  todos. Arbitrary reference navigation is likewise deferred to the API projection
  boundary, where links will be parsed and restricted to http(s).

## Non-blocking unrelated test observation

`uv run pytest tests/test_web.py -q` produced 7 passes and 2 pre-existing
environment-dependent failures outside this contract seam: the default app attempted to
parse a changed live NASDAQ response, and the health assertion observed `llm_mode=local`
where the test expects `mock`. No configuration or environment file was inspected or
changed, and no test was weakened. The focused contract and evidence-trace suites above
remain green.

## Risks / handoff

- Role services do not populate the new detail yet; default placeholders are intentional
  until Todo 2 captures typed facts.
- The raw `reference` text is retained for later safe projection. It is not a navigable
  link in this task; Todo 3 must restrict clickability to parsed http(s) references.

## Todo 2 contract addendum — strategist conviction

- Added nullable `StrategyDetail.conviction`, bounded inclusively to `0.0`–`1.0` and
  defaulting to `None`; this preserves frozen, strict, legacy-placeholder behavior.
- The terminal-detail JSON round-trip now retains `conviction=0.82`; parametrized
  boundary probes reject `-0.01` and `1.01`.
- Focused verification: `6 passed`; Ruff format/check passed; basedpyright reported
  `0 errors, 0 warnings, 0 notes`.
- Manual `uv run python` proof serialized and restored the value, then confirmed an
  out-of-range runtime construction was rejected. No Docker, database, environment
  file, network resource, or secret was accessed; no cleanup was needed.
