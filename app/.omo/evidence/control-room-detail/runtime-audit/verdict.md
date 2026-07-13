# Runtime audit verdict — PostgreSQL terminal detail

## Verdict

**PASS — CONFIRMED.**

The administrator terminal detail survives real disposable PostgreSQL persistence and rehydration. The live ASGI endpoint returned collection, strategist, and critic fields after the run was persisted. `sec://filing/fixture-filing` remained a readable non-web reference with `href: null`; it was not converted to a link.

## Runtime evidence

- Command: `sh scripts/test_postgres_integration.sh -q tests/integration/test_domain_lifecycle_postgres.py`
- Result: `20 passed in 9.13s`
- Observed path: pipeline execution → `PostgresRunStore` terminal persistence → newly configured PostgreSQL-backed ASGI app → `GET /api/runs/{run_id}/detail`.
- Response assertions covered:
  - disclosure and news collection facts
  - strategist proposal, rationale, gate, blockers, and conviction
  - critic verdict, rationale, and layer
  - `sec://filing/fixture-filing` as `{ "label": "sec://filing/fixture-filing", "href": null }`

## Hypotheses

| ID | Result | Runtime disposition |
| --- | --- | --- |
| H1 | Confirmed | Full terminal detail persisted and rehydrated. |
| H2 | Refuted | No omission or parse failure occurred. |
| H3 | Refuted | `sec://` remained non-clickable. |

## Constraints and cleanup

- Used only the script-owned disposable PostgreSQL runner.
- Did not inspect, use, stop, or change localhost:5432 or product Docker/Compose resources.
- The runner cleanup trap removed its temporary container on exit.
- No debug listener, temporary source change, credential, or secret record was created.
