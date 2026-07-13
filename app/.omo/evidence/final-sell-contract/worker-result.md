# Strategist sell-contract worker result

## Scope

- `Side` now contains only the MVP strategist actions: `buy` and `hold`.
- `tb_strategist_signals.side` now has the same two-value PostgreSQL CHECK.
- `tb_fill.side` remains independently constrained to `buy` and `sell`; no execution or paper-only broker gate changed.

## Baseline and red regressions

Before the change, the existing deterministic role tests characterized both allowed MVP outcomes:

```text
uv run pytest -q tests/unit/test_ontology.py tests/unit/test_roles_05_08_contracts.py \
  -k 'logical_enums or strategy_output_downgrades_buy_when_hard_blocked or strategy_output_uses_injected_confidence_threshold'
3 passed, 53 deselected
```

The newly written negative tests failed before the implementation change:

```text
uv run pytest -q tests/unit/test_ontology.py -k phase_two_sell
FAILED: {'buy', 'hold', 'sell'} != {'buy', 'hold'}

sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py -k phase_two_sell
FAILED: DID NOT RAISE IntegrityError
```

The second command used the project disposable runner only.

## Green verification and manual data-surface QA

```text
uv run pytest -q tests/unit/test_ontology.py tests/unit/test_roles_05_08_contracts.py \
  -k 'phase_two_sell or logical_enums or strategy_output_downgrades_buy_when_hard_blocked or strategy_output_uses_injected_confidence_threshold'
5 passed, 53 deselected

uv run pytest -q tests/integration/test_schema_sql.py
5 passed

sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py \
  -k 'phase_two_sell or rejects_orphan_technical_snapshot'
2 passed, 17 deselected

uv run ruff format --check <five changed Python files>
5 files already formatted
uv run ruff check <five changed Python files>
All checks passed!
uv run basedpyright <five changed Python files>
0 errors, 0 warnings, 0 notes
```

Manual QA was the real disposable PostgreSQL surface: after inserting valid parent `tb_universe` and `tb_daily_pick` rows, an INSERT with `tb_strategist_signals.side='sell'` raised `IntegrityError` from the actual database CHECK.

## Adversarial and cleanup results

- Direct enum parsing rejects `Side('sell')`.
- The Pydantic `StrategyOutput` model rejects `side='sell'`.
- `tb_fill.side` catalog expectation remains `('buy', 'sell')`.
- The disposable runner dynamically chose a loopback port in its reserved `55400-55499` range and its trap removed its UUID-named test container. No configured product database or existing Docker resource was targeted.

## Documentation note

The canonical design already identifies strategist `sell` as phase 2. The pre-change statement in `.omo/evidence/final-f4/README.md` is historical evidence and is intentionally left untouched for the final F4 owner to replace with fresh evidence.
