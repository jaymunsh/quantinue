---
slug: quantinue-control-room-detail
status: planned
intent: clear
pending-action: user chooses start work or optional high-accuracy plan review
approach: Persist one redacted administrator decision brief on terminal runs, project it through dedicated API view models, and render collection-to-critic cards without exposing raw or unsafe content.
---

# Draft: quantinue-control-room-detail

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| terminal-detail | A completed run retains collection, strategy, and critic display facts | active | API/dashboard contract tests |
| admin-projection | API exposes a dedicated redacted control-room detail view | active | schema and response tests |
| admin-ui | Dashboard presents the collection → strategist → critic narrative responsively | active | browser screenshots and DOM assertions |
| safety | Links and text remain bounded and safe; raw/provider-sensitive data remains excluded | active | adversarial projection tests |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| show summaries, not raw source/provider payloads | bounded typed display copy only | raw values are not stored safely and violate the design contract | yes |
| link only http(s) sources | non-http references remain visible text | existing fixture and SEC references are not browser-safe URLs | yes |
| render the latest terminal run | no scheduler/live refresh additions | user requested first-run administrative confirmation | yes |

## Findings (cited - path:lines)

- `PipelineContext` retains `disclosure_source`, `news_source`, scores, side, and conviction, but `PipelineContext.to_run()` drops those display details: `src/quantinue/core/contracts.py`.
- Role 07 receives `StrategyOutput.summary`; role 08 has structured hard-gate/model verdict facts, but both only emit localized stage text: `src/quantinue/roles/role_07_strategist/service.py`, `src/quantinue/roles/role_08_critic/service.py`.
- `ControlRoomRun` currently projects stage summaries and evidence metadata only: `src/quantinue/api/schemas.py`, `src/quantinue/main.py`, `src/quantinue/web/templates/dashboard.html`.
- `source_ref` is not necessarily a web URL, and raw LLM reasons are unbounded; direct template rendering/linking is unsafe: role 05/06 sources and Metis review.
- `DESIGN.md` requires dense evidence, responsive readability, redaction, and no document overflow at 390/768/1024/1440.

## Decisions (with rationale)

- Add a small terminal-run administrator detail contract, not UI parsing of stage summaries.
- Retain only typed, bounded display fields; preserve the current no-raw-prompt/no-raw-provider-payload rule despite the user requesting a visually rich admin page.
- Use semantic cards and native `<details>` disclosure for long collection/report content; no JavaScript or scheduler is required.

## Scope IN

- Persist and project safe collection summaries, score comparisons, strategist rationale/gate state, and critic verdict facts.
- Add an admin-first dashboard section and responsive styling.
- Add unit/API/template/browser regressions for happy, blocked, legacy, unsafe-link, and long-content cases.

## Scope OUT (Must NOT have)

- No scheduler, polling, live trading, raw provider payloads, prompts, credentials, raw exceptions, or arbitrary-link navigation.
- No new external data source or LLM provider behavior.

## Open questions

- None. The user requested a fast administrator-first view; the reversible safe-display defaults above are adopted.

## Approval gate
status: approved-for-plan
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
