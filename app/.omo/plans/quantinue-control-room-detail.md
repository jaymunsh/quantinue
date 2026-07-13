# quantinue-control-room-detail - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** 관리자가 한 번의 01–11 실행에서 수집 요약, 점수, strategist 제안 근거, critic 판정을 한 흐름으로 확인하는 상세 운영실 화면.

**Why this approach:** 실행 단계의 짧은 문구를 해석하지 않고, 안전한 관리자용 구조화 데이터를 완료 실행에 보존해 API와 화면이 같은 사실을 표시한다.

**What it will NOT do:** 스케줄러·폴링·실거래·새 수집 공급자는 추가하지 않는다. 비밀값, 프롬프트, 원시 외부/모델 페이로드, 원시 오류도 표시하지 않는다.

**Effort:** Medium
**Risk:** Medium - 완료 실행 계약을 확장하므로 메모리·PostgreSQL·API 투영의 동기화가 필요하다.
**Decisions to sanity-check:** 관리자 화면은 원문이 아닌 안전하게 제한된 요약과 검증된 http(s) 링크만 표시한다.

Your next move: 이 계획을 실행해 달라고 말해 주세요. Full execution detail follows below.

---

> TL;DR (machine): medium-risk TDD detail-contract, API projection, server-rendered admin cards, and browser QA; no scheduler or unsafe payload exposure.

## Scope
### Must have
- Terminal-run administrator detail contract for collection summaries/scores, strategist rationale/gates, and critic verdict facts.
- Dedicated redacted API projection and a server-rendered latest-run detail section.
- Bounded text and http(s)-only navigable source links; non-web source references remain readable text.
- Contract, API/template, responsive browser, and disposable-PostgreSQL persistence coverage.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not add scheduler/polling/real-trading behavior, new providers, raw source/provider payloads, prompts, credentials, raw exception messages, or arbitrary URL links.
- Do not parse localized stage summary strings as data or weaken existing append-only/paper-only boundaries.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD with pytest/FastAPI TestClient, disposable PostgreSQL, and Playwright Chromium.
- Evidence: `.omo/evidence/control-room-detail/task-<N>.md`.

## Execution strategy
### Parallel execution waves
- Wave 1: terminal detail contract extraction, role-detail capture, and URL/text safety helpers.
- Wave 2: API projection and dashboard section after the contract is stable.
- Wave 3: responsive browser and PostgreSQL persistence verification.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 3, 4 | 3 |
| 2 | 1 | 4, 5 | 3 |
| 3 | 1 | 4, 5 | 2 |
| 4 | 1, 2, 3 | 5 | none |
| 5 | 2, 3, 4 | final wave | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Extract a bounded terminal administrator-detail contract without increasing oversized core modules.
  What to do / Must NOT do: Move or split terminal run types as necessary so a typed detail object can be persisted with `PipelineRun` while product Python files stay at or below 250 pure LOC. Define display-safe collection, strategy, and critic records with explicit defaults for legacy/partial runs. Do not store raw prompts, raw model/provider payloads, credentials, or exception strings.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 3, 4
  References (executor has NO interview context - be exhaustive): `src/quantinue/core/contracts.py`, `src/quantinue/core/schemas.py`, `src/quantinue/api/schemas.py`, `src/quantinue/db/codec.py`, `DESIGN.md` sections 5 and 7.
  Acceptance criteria (agent-executable): red tests prove JSON round-trip and legacy terminal-run parsing; `uv run ruff check`, `uv run basedpyright`, and a pure-LOC scan are clean.
  QA scenarios (name the exact tool + invocation): happy terminal run retains detail; failure/legacy terminal run renders safe empty placeholders, Evidence `.omo/evidence/control-room-detail/task-1.md`.
  Commit: N | feat(contract): retain redacted administrator detail

- [x] 2. Capture typed source, strategist, and critic facts at roles 05–08.
  What to do / Must NOT do: Carry existing disclosure/news title-summary-source-score facts, `StrategyOutput.summary`/blockers/gate, and a typed critic decision/reason/layer through `PipelineContext` into the new detail contract. Keep model output schema-bound and cap display text; never infer facts from localized stage summaries.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4, 5
  References (executor has NO interview context - be exhaustive): `src/quantinue/roles/role_05_disclosure_analysis/service.py`, `src/quantinue/roles/role_06_news_analysis/service.py`, `src/quantinue/roles/role_07_strategist/contracts.py`, `src/quantinue/roles/role_07_strategist/service.py`, `src/quantinue/roles/role_08_critic/contracts.py`, `src/quantinue/roles/role_08_critic/service.py`, `src/quantinue/core/contracts.py`.
  Acceptance criteria (agent-executable): focused role/pipeline tests assert fixture summaries, scores, strategist rationale/gate, critic hard/model verdict and legacy defaults; no source file exceeds 250 pure LOC.
  QA scenarios (name the exact tool + invocation): happy buy/pass detail; hard-block/hold detail and long reason truncation, Evidence `.omo/evidence/control-room-detail/task-2.md`.
  Commit: N | feat(roles): retain administrator decision facts

- [x] 3. Create safe display/link projection helpers and API view models.
  What to do / Must NOT do: Project the terminal detail into dedicated frozen API view models. Permit clickable links only for parsed `http`/`https` URLs; render `sec://`, `fixture://`, and malformed values as non-clickable references. Escape/bound text at the typed projection boundary; preserve current evidence and redacted attempt projection behavior.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4, 5
  References (executor has NO interview context - be exhaustive): `src/quantinue/api/schemas.py`, `src/quantinue/main.py`, `src/quantinue/api/presentation.py`, `src/quantinue/core/contracts.py`, `src/quantinue/web/templates/dashboard.html`, `tests/test_web.py`.
  Acceptance criteria (agent-executable): API tests validate the new detail response; adversarial URL/reason/raw-error values cannot become links or rendered sensitive content; type/static checks clean.
  QA scenarios (name the exact tool + invocation): valid public URL link versus `sec://` plain text and hostile text suppression, Evidence `.omo/evidence/control-room-detail/task-3.md`.
  Commit: N | feat(api): project safe execution detail

- [x] 4. Render the latest-run collection-to-critic administrator brief.
  What to do / Must NOT do: Add a semantic latest-run section ahead of the generic evidence ledger: collection cards, score comparison, strategist proposal/rationale/gates, critic decision/objection/layer, and unavailable/blocked state. Use native disclosure elements for long copy, existing design tokens, and responsive CSS; update `DESIGN.md` with any new reusable primitives. Do not introduce client JavaScript, external assets, unsafe `href`, or a scheduler.
  Parallelization: Wave 2 | Blocked by: 1, 2, 3 | Blocks: 5
  References (executor has NO interview context - be exhaustive): `DESIGN.md`, `src/quantinue/web/templates/dashboard.html`, `src/quantinue/web/static/dashboard.css`, `src/quantinue/main.py`, `src/quantinue/api/schemas.py`.
  Acceptance criteria (agent-executable): rendered fixture dashboard includes collection/strategy/critic sections and stable empty/blocked placeholders; keyboard focus, native disclosure, and reduced motion are retained.
  QA scenarios (name the exact tool + invocation): desktop/mobile completed run and no-detail legacy run, Evidence `.omo/evidence/control-room-detail/task-4.md`.
  Commit: N | feat(web): show administrator decision brief

- [x] 5. Verify persistence, responsive UI, and full regression gates.
  What to do / Must NOT do: Add/update disposable PostgreSQL integration coverage for terminal detail persistence and API rehydration, then run targeted/full static and test gates. Drive the running control room through real Chromium at 1440/1024/768/390, including a safe external source link, a non-web source reference, long rationale, and blocked/empty state. Do not inspect or alter host localhost:5432 resources.
  Parallelization: Wave 3 | Blocked by: 2, 3, 4 | Blocks: final wave
  References (executor has NO interview context - be exhaustive): `scripts/test_postgres_integration.sh`, `scripts/test_compose_contract.sh`, `tests/integration`, `tests/test_web.py`, `DESIGN.md` sections 4, 6, 7.
  Acceptance criteria (agent-executable): Ruff format/check, basedpyright, pytest, disposable PostgreSQL, Compose contract, and browser DOM/console/overflow assertions all pass; scoped runtime cleanup receipt exists.
  QA scenarios (name the exact tool + invocation): complete and blocked runs at every viewport; malformed URL and raw-sensitive value remain safe, Evidence `.omo/evidence/control-room-detail/task-5.md`.
  Commit: N | test(control-room): verify detailed administrator view

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit
- [x] F2. Code quality review
- [x] F3. Real manual QA
- [x] F4. Scope fidelity

## Commit strategy

No commits unless the user explicitly requests Git work.

## Success criteria

- A terminal execution exposes an administrator-readable collection → strategist → critic narrative without parsing stage text.
- Collection links are only navigable for validated http(s) sources; non-web references remain visible text.
- Legacy, partial, failed, and blocked runs remain renderable and redacted.
- The detail section is readable without horizontal overflow at 390, 768, 1024, and 1440 pixels.
- No scheduler or unsafe raw content is added.
