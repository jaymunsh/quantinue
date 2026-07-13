# Task 2 — typed role detail capture

## Delivered

- Role 05 and 06 collection records now project title, summary, source, reference, and score
  from `PipelineContext` into the bounded terminal detail.
- Role 07 retains its typed `StrategyOutput`; the terminal projection retains proposal,
  bounded rationale, code-gate outcome, blockers, and conviction without parsing stage text.
- Role 08 retains a typed `CriticVerdict` for no-buy, hard-gate, and model paths. Its
  terminal projection exposes only decision, bounded rationale, and decision layer.
- Long collection and model-derived display text is truncated to the terminal-contract
  limits before persistence. Prompts, raw provider payloads, credentials, and exceptions
  are never stored in the detail projection.

## TDD and focused verification

The initial focused run failed as expected: the completed fixture pipeline returned the
legacy empty detail placeholders, and the critic neither consumed `macro_regime` nor
retained its hard-gate verdict. After the implementation:

```text
uv run pytest -q tests/unit/test_pipeline_terminal_detail.py \
  tests/unit/test_terminal_detail_contract.py \
  tests/unit/test_roles_05_08_contracts.py \
  tests/unit/test_pipeline_evidence_trace.py
88 passed in 1.13s

uv run ruff format --check <five changed Python paths>
5 files already formatted
uv run ruff check <same paths>
All checks passed!

uv run basedpyright <same paths>
0 errors, 0 warnings, 0 notes
```

The focused tests cover the completed buy/pass path, a `risk_off` hard rejection, a
failed terminal run retaining already-collected detail, empty legacy context placeholders,
and truncation of a 1,001-character strategist rationale.

## Manual runtime proof

Executed the real offline 11-role fixture pipeline with `build_default_orchestrator()`:

```text
{'stages': 11,
 'disclosure': ('Deterministic fixture filing', 0.78),
 'news': ('Deterministic fixture news', 0.74),
 'strategy': ('buy', 'passed', 0.775),
 'critic': ('pass', 'gate')}
```

This used the in-memory fixture runtime only. No Docker resource, PostgreSQL resource,
network service, environment file, broker, secret, or external data source was used.
No cleanup was required because the in-memory store ended with the process.

## Adversarial probes

- Hard gate: `macro_regime='risk_off'` produces retained `reject`, `risk-off regime`,
  and `hard_rule` detail.
- Text boundary: a 1,001-character `StrategyOutput.summary` becomes a 1,000-character
  terminal rationale.
- Legacy context: absent role results produce the explicit empty detail placeholders.
- Partial failure: a real two-role in-memory run persists completed collection detail when
  its following role fails.
- Data boundary: all terminal detail remains frozen, strict, and extra-field-forbidden
  under the Task 1 contract tests.

## Scope and risks

- This task does not make source references navigable; Todo 3 owns validated http(s)
  projection and template links.
- This task does not change database schema or append-only persistence behavior. Existing
  `PipelineRun` JSON persistence carries the detail field unchanged.
