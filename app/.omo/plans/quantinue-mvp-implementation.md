# quantinue-mvp-implementation - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** API 키 없이 01~11 전체 파이프라인을 재현하고, 실행 근거·실패·체크포인트·주문·리뷰까지 운영실과 PostgreSQL에서 추적할 수 있는 1차 MVP. OpenAI와 Alpaca paper 키를 넣으면 opt-in 통합 테스트를 바로 실행할 수 있다.

**Why this approach:** 설계서가 지정한 기계 정본을 먼저 고정하고 모든 역할과 어댑터가 그 타입을 소비하게 한다. 외부 서비스는 동일한 좁은 인터페이스 뒤에 두어 offline 테스트와 실제 연동의 의미가 갈라지지 않게 한다.

**What it will NOT do:** 실거래, 다계좌, 능동 매도, 트레일링 스톱, 멀티턴 토론, ML 가격 예측은 포함하지 않는다. 기존 localhost:5432 서비스나 볼륨은 변경하지 않는다.

**Effort:** XL
**Risk:** High - 전체 도메인 스키마, 재시작 가능한 오케스트레이션, 외부 주문 멱등성이 동시에 바뀐다.
**Decisions to sanity-check:** Alpaca paper-only 삼중 안전 게이트, 기본 offline fixture, 5444 loopback DB 노출.

Your next move: 실행 중. Full execution detail follows below.

---

> TL;DR (machine): XL/high-risk TDD implementation of canonical contracts, 11 role boundaries, resilient orchestration, paper adapters, isolated Docker, docs, and UI QA.

## Scope
### Must have
- `src/quantinue/core/ontology.py`와 작은 공통 Pydantic 모델 모듈들에 설계서의 확정 ENUM, 엔터티, 이벤트, evidence, decision, order, review 계약 구현.
- `db/schema.sql`, `src/quantinue/core/schemas.py`/ontology, `config/*.yaml` 간 PK/FK/UNIQUE/점수/시각/임계값 일치.
- 활성 도메인 테이블 15개(`tb_universe`, `tb_daily_pick`, `tb_technical`, `tb_macro`, `tb_disclosure`, `tb_disclosure_signal`, `tb_news`, `tb_news_signal`, `tb_strategist_signals`, `tb_critic_verdict`, `tb_account`, `tb_order`, `tb_fill`, `tb_review_price_snapshots`, `tb_review`)와 별도 운영 테이블 `pipeline_runs`, `pipeline_stage_attempts`, `pipeline_checkpoints`, `order_submissions`.
- 01~11 각 역할의 명시적 input/output Pydantic 계약과 경계 검증, 독립 시스템 prompt 리소스.
- deterministic mock, OpenAI, OpenAI-compatible local LLM, mock broker, Alpaca paper adapter의 동일 인터페이스.
- run ID, stage attempt, source/evidence timestamps, confidence, input hash, model/prompt metadata 추적.
- typed failure, per-stage timeout, transient-only retry, atomic checkpoint/resume, concurrent duplicate run/order prevention.
- Quantinue Postgres host `127.0.0.1:5444`, Docker internal `db:5432`, secrets-free `.env.example`.
- 운영실에 실행/단계/근거/실패/주문/리뷰 표시와 responsive accessibility.
- 설계 요구사항→구현/테스트 매핑 문서와 unit/Postgres/API/Docker/responsive test gates.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- 기존 `localhost:5432` 컨테이너, 볼륨, 네트워크를 stop/remove/recreate/configure하지 않는다.
- Alpaca live endpoint 또는 기본 활성 주문을 허용하지 않는다.
- 비밀값을 파일, 로그, ledger, 테스트 artifact에 기록하지 않는다.
- 다계좌, 부분체결 완전 상태기계, 능동 매도, trailing stop, 멀티턴, ML을 MVP에 끌어오지 않는다.
- 미확정 설계값은 `IMPLEMENTATION_ASSUMPTIONS.md`에 보수적 기본값과 근거를 기록한다: snapshot freshness 5분, weak evidence는 hold, late-entry는 03의 확정 게이트만 사용, critic은 `UNIQUE(signal_id)` 단일 판정, review source는 `fixture|market_data`, order type/status는 구현한 paper 흐름의 닫힌 집합만 허용한다.
- 제품 Python 파일은 250 pure LOC를 넘기지 않고 public `Any`/`dict`/`cast`/type-ignore/broad except를 만들지 않는다.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD with pytest, FastAPI TestClient/httpx wire fakes, and real PostgreSQL/Docker smoke.
- Evidence: `.omo/evidence/task-<N>-quantinue-mvp-implementation.*`; no secrets or raw environment dumps.

## Execution strategy
### Parallel execution waves
- Wave 1: Todos 1-3 (contract/schema, config/provider seams, orchestration state design) with exclusive file ownership.
- Wave 2: Todos 4-6 after canonical contracts land (role implementations, persistence/resilience, adapters/order safety).
- Wave 3: Todos 7-8 after API shapes stabilize (docs/Docker and control room/full verification).

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 4,5,6,7,8 | 2,3 |
| 2 | none | 4,6,7 | 1,3 |
| 3 | none | 5,8 | 1,2 |
| 4 | 1,2 | 8 | 5,6 |
| 5 | 1,3 | 8 | 4,6 |
| 6 | 1,2 | 7,8 | 4,5 |
| 7 | 1,2,6 | 8 | none |
| 8 | 1-7 | final wave | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Canonical ontology, domain schemas, DDL, and threshold contract
  What to do / Must NOT do: Write failing tests that extract/encode finalized design enums, score bounds, UTC timestamps, NY trade dates, identifiers, entity/event/evidence/decision/order/review models, then implement `core/ontology.py`, `core/schemas.py` and focused model modules plus all 15 named domain tables and four named operational tables in `db/schema.sql`. Keep Postgres logical enums as TEXT. Operational tables satisfy the user's 1st-phase tracking override but must not become domain FK parents. Record conservative defaults for unresolved design fields in assumptions.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 4,5,6,7,8
  References: `../docs/quantinue-integrated-design.html` sections `#conv`, `#erd`, `#s01`..`#s11`, `#relay`, `#ai`; `src/quantinue/core/contracts.py`; `db/schema.sql`; `config/pipeline.yaml`.
  Acceptance criteria: `uv run pytest tests/unit/test_ontology.py tests/unit/test_schemas.py tests/integration/test_schema_sql.py`; explicit catalog assertions for every named table and PK/FK/UNIQUE/CHECK; reject naive/future-invalid lineage timestamps, missing source snapshot, unknown enum and out-of-range score; ruff/basedpyright pass for changed files. Bootstrap is idempotent fresh/scaffold DB SQL, no Alembic and no destructive migration of unknown user data.
  QA scenarios: happy `psql` loads schema into disposable Quantinue DB and queries catalog constraints; failure submits unknown event_type/naive datetime/out-of-range confidence and gets Pydantic rejection. Evidence `.omo/evidence/task-1-*`.
  Commit: N | feat(contract): implement canonical domain contract

- [x] 2. Configuration, prompts, and provider interfaces
  What to do / Must NOT do: TDD typed settings for timeouts/retries/models/paper endpoint; split prompts into package resources for 05 disclosure, 06 news, 07 strategist, 08 critic, and 11 reviewer; create role-neutral typed LLM/provider protocol implemented by deterministic mock, OpenAI, and local OpenAI-compatible adapters. Track prompt/model/policy version and input hash in operational metadata (explicit user override of design phase-2 timing). Load full prompt semantics without exact-string snapshot tests. No secrets or permissive live URL.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 4,6,7
  References: `src/quantinue/core/config.py`, `src/quantinue/llm/provider.py`, role 05-08 services, `.env.example`, `config/pipeline.yaml`, design `#s05`..`#s08`.
  Acceptance criteria: provider contract tests prove identical parsed outputs; all five prompt resources are packaged and loader failure is typed; adapters receive identical prompt/version metadata; missing credentials fail startup only in selected real mode; local base URL example works with wire fake; malicious news instructions remain quoted data and schema-bound output; secret redaction test passes.
  QA scenarios: happy launch offline and local wire-fake configurations; failure select OpenAI with empty key and receive redacted typed config error. Evidence `.omo/evidence/task-2-*`.
  Commit: N | feat(adapters): separate prompts and llm providers

- [x] 3. Run/stage lifecycle and retry/checkpoint policy contracts
  What to do / Must NOT do: TDD a closed run/stage state machine, attempt/checkpoint models, deterministic idempotency keys/input hashes, injected clock, timeout/retry classifier and bounded backoff policy. Distinguish failed/skipped/blocked/retrying/completed; never retry validation, hard-risk, auth, or non-transient 4xx.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 5,8
  References: `src/quantinue/orchestration/pipeline.py`, `src/quantinue/core/errors.py`, `src/quantinue/db/store.py`, design scheduling/relay/MVP sections.
  Acceptance criteria: deterministic unit tests cover every state transition, timeout, retry exhaustion, resume boundary, repeated interruption and idempotency-key stability with no sleeps.
  QA scenarios: happy simulated transient failure succeeds on bounded retry; failure validation error makes one attempt and persists typed failure. Evidence `.omo/evidence/task-3-*`.
  Commit: N | feat(orchestration): define resilient execution state

- [x] 4. Implement explicit 01-11 role contracts and services
  What to do / Must NOT do: For each role add immutable typed input/output contract, required/nullable fields, enums, score/timestamp/cross-field validators and service tests before replacing scaffold fields. Implement optional no-key public adapters for NASDAQ screener (01), market candles (02), public macro fixture/feed seam (04), SEC submissions (05), and RSS title/snippet (06), all behind the same interfaces with deterministic offline fixtures as default. Preserve source/evidence lineage and design gates/buckets/critic/risk/review semantics. LLM never decides code-enforced gates. Add injected clock/calendar seam and fixture T+1..T+5 including weekend/holiday/DST boundaries. Keep each source file ≤250 pure LOC.
  Parallelization: Wave 2 | Blocked by: 1,2 | Blocks: 8
  References: every `src/quantinue/roles/role_*/service.py`, canonical models from Todo 1, provider protocol from Todo 2, design `#s01`..`#s11` and `#relay`.
  Acceptance criteria: parametrized contract tests cover valid output and missing/stale (>5 minutes)/future/contradictory upstream inputs for all 11 roles; public adapters have wire-level tests and bounded timeouts; offline 01→11 emits linked evidence and correct terminal order/review state; fake-calendar T+5 uses fill price for buy and decision close for hold across weekend/holiday/DST.
  QA scenarios: happy run NVDA fixture through every boundary; failure stale evidence or hard blocker yields hold/reject with no order. Evidence `.omo/evidence/task-4-*`.
  Commit: N | feat(roles): implement role-specific contracts

- [x] 5. PostgreSQL persistence, atomic checkpoints, and resumable orchestration
  What to do / Must NOT do: Replace snapshot-only store with repository interfaces and SQLAlchemy/SQL primitives matching canonical DDL; claim a run atomically, persist attempts/checkpoints/evidence, resume after last completed stage, and use database uniqueness/upsert semantics under concurrency. Keep in-memory fake behaviorally equivalent.
  Parallelization: Wave 2 | Blocked by: 1,3 | Blocks: 8
  References: `src/quantinue/db/store.py`, `src/quantinue/orchestration/pipeline.py`, `src/quantinue/main.py`, canonical DDL and lifecycle models.
  Acceptance criteria: real disposable PostgreSQL integration tests prove two concurrent identical runs resolve to one execution, interrupted run resumes, failed run remains observable, and no completed checkpoint repeats.
  QA scenarios: happy kill/recreate web process then resume same cycle; failure inject stage timeout and query persisted failure/attempt. Evidence `.omo/evidence/task-5-*`; teardown receipt required.
  Commit: N | feat(persistence): add atomic checkpoints and resume

- [x] 6. Broker adapters and duplicate-order safety
  What to do / Must NOT do: TDD common broker protocol, deterministic mock and Alpaca paper adapter with bracket validation, 0-quantity no-submit, stable client order ID, pre-submit DB reservation, retry-safe lookup/reconciliation for timeout-before/after acceptance, and triple safety gate. Restrict endpoints to Alpaca paper; redact headers/errors. Support submitted/accepted/filled/canceled/rejected observability needed for reconciliation, but exclude a complete partial-fill lifecycle.
  Parallelization: Wave 2 | Blocked by: 1,2 | Blocks: 7,8
  References: `src/quantinue/broker/provider.py`, role 09/10, config, canonical order/fill models, design `#s09`, `#s10`, AI #15.
  Acceptance criteria: HTTP wire-fake tests cover success, timeout-after-accept then lookup, duplicate response, 401 no retry, malformed response, and trading lock; concurrent submissions cause exactly one POST.
  QA scenarios: happy submit against local wire fake and inspect one redacted request; failure configure live URL or disabled trading and assert zero network calls. Evidence `.omo/evidence/task-6-*`.
  Commit: N | feat(broker): harden Alpaca paper order execution

- [x] 7. Isolated Docker/env and implementation mapping documentation
  What to do / Must NOT do: Publish only Quantinue DB as `127.0.0.1:5444:5432`; retain web 8011; add schema initialization/healthcheck without touching external projects. Expand secret-free `.env.example` with local host/Docker DB URLs, OpenAI/local LLM/Alpaca paper setup and safe opt-in commands. Write design requirement→code→test mapping and operations/recovery guide; update README/assumptions.
  Parallelization: Wave 3 | Blocked by: 1,2,6 | Blocks: 8
  References: `compose.yaml`, `Dockerfile`, `.env.example`, `README.md`, `IMPLEMENTATION_ASSUMPTIONS.md`, all implemented contracts/tests.
  Acceptance criteria: `docker compose config` shows exactly `127.0.0.1:5444:5432` for Quantinue and internal `db:5432`; separate Compose project/volume names are used; secret scan finds no actual key; mapping accounts for user requirements 1-11 plus `#conv/#erd/#s01-#s11/#relay/#security`; tests and cleanup address Quantinue resources only and never connect to, stop, remove, or inspect data in localhost:5432.
  QA scenarios: happy isolated compose project starts and health/API work via 8011/5444; failure host 5444 occupied produces bounded clear failure without fallback to 5432. Evidence `.omo/evidence/task-7-*`; compose teardown receipt required.
  Commit: N | docs(operations): document safe integration setup

- [x] 8. Control room observability and complete automated/visual QA
  What to do / Must NOT do: Update API/UI to show run status, stage attempts/timings, evidence/source/confidence, checkpoints, failures, order idempotency and review state while preserving accessible server-rendered UI. Add API E2E, Docker smoke, responsive and reduced-motion tests. Do not expose prompts, secrets or raw sensitive errors.
  Parallelization: Wave 3 | Blocked by: 1-7 | Blocks: final wave
  References: `src/quantinue/main.py`, `src/quantinue/api/schemas.py`, `src/quantinue/web/templates/dashboard.html`, `src/quantinue/web/static/dashboard.css`, current tests, all new repositories/models.
  Acceptance criteria: full `ruff format --check`, `ruff check`, `basedpyright`, `pytest` pass; dashboard assertions cover empty/running/retrying/failed/completed and API/UI values match; screenshots at 1440/1024/768/390 prove zero document horizontal overflow, mobile table/card readability, visible evidence/error/checkpoint state, keyboard focus and reduced-motion behavior. Real-key tests are excluded by default, skip with explicit reason when keys are absent, and require an opt-in marker/environment flag plus paper-only cleanup runbook when enabled.
  QA scenarios: happy launch mock pipeline from real browser and inspect 11 linked stages; failure inject timeout and see actionable redacted error with retry/checkpoint state. Evidence `.omo/evidence/task-8-*`; browser/server cleanup receipts required.
  Commit: N | feat(control-room): expose resilient pipeline operations

## Final remediation wave

- [x] R1. Preserve immutable append-only source, signal, and decision provenance
  Acceptance criteria: repeated identical raw/source/signal/strategist/critic writes are idempotent; conflicting replay cannot overwrite the first row's raw, source, evidence, parent, model, prompt, policy, input-hash, or other provenance values; `tb_review_price_snapshots` remains freshness-updatable. A real disposable PostgreSQL regression verifies the boundary through `scripts/test_postgres_integration.sh` without touching 5432/5444.

- [x] R2. Enforce the MVP buy/hold-only strategist contract
  Acceptance criteria: `Side` and `tb_strategist_signals.side` accept only buy/hold, contracts/expectations/docs agree, and model plus real disposable PostgreSQL regression tests reject sell. Existing paper-only order safety stays unchanged; `tb_fill` is not narrowed by this strategist requirement.

- [x] R3. Restore final static quality without retry-policy regression
  Acceptance criteria: stale duplicated failure classification is removed, `failure_policy.py` is formatted, review processor imports/noqa are clean, and targeted retry/failure behavior remains verified.

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit
- [x] F2. Code quality review
- [x] F3. Real manual QA
- [x] F4. Scope fidelity

## Completion safeguards

- [x] G1. Global five-lane review-work gate
  Completed: goal/constraint, hands-on QA, code quality, security, and context-mining lanes independently PASS; evidence `.omo/evidence/final-g1/verdict.md`.

- [x] G2. Final three-hypothesis runtime debug audit and redacted ledger entry
  Completed: H1 append-only replay, H2 strategist sell boundary, and H3 retry/terminal classification are refuted with runtime evidence; `.omo/evidence/runtime-debug-audit/verdict.md` and ledger entry recorded.

## Commit strategy

No commits unless the user explicitly requests Git work. Preserve the untracked/dirty workspace; never reset, checkout, clean, or overwrite unrelated files.

## Success criteria

- Offline `mock + memory` and `mock + PostgreSQL` modes finish 01→11 without credentials and preserve traceable evidence.
- OpenAI/local LLM and Alpaca paper modes are selectable without role changes; missing credentials and unsafe endpoint fail closed.
- Restart, timeout, transient retry and concurrent duplicate requests have deterministic tests and persisted observable outcomes.
- Compose exposes Quantinue PostgreSQL only on loopback 5444 while containers use db:5432; existing localhost:5432 resources are unchanged.
- All quality and visual gates pass with redacted evidence and cleanup receipts; mapping documentation covers every requested requirement.
