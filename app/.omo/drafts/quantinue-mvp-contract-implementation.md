# Quantinue MVP Contract Implementation — Durable Draft

- intent: clear
- review_required: false
- size: architecture
- status: awaiting-approval
- pending_action: write `.omo/plans/quantinue-mvp-contract-implementation.md`
- test_strategy: TDD (unit + PostgreSQL integration + API/E2E + Docker smoke + responsive visual QA)

## Objective

`../docs/quantinue-integrated-design.html`을 사람용 원본 계약으로 사용해 API 키 없는 01→11 1차 MVP를 완성하고, 사용자가 OpenAI 및 Alpaca paper 키만 넣으면 실제 통합 테스트할 수 있는 상태로 만든다.

## Components ledger

| ID | Outcome | Status | Evidence |
|---|---|---|---|
| C1 | ontology, 공통 Pydantic 모델, 전체 PostgreSQL DDL, YAML 임계값을 기계 정본으로 일치시킨다 | grounded | `../docs/quantinue-integrated-design.html`, `src/quantinue/core/contracts.py`, `db/schema.sql`, `config/pipeline.yaml` |
| C2 | 01~11 각각에 독립 입력/출력 계약, 경계 검증, 프롬프트 파일, mock/real adapter seam을 구현한다 | grounded | `src/quantinue/roles/role_*/service.py`, `src/quantinue/llm/provider.py`, `src/quantinue/broker/provider.py` |
| C3 | 실행 ID, 근거/출처/시각/신뢰도, 실패/타임아웃/재시도/체크포인트, 주문 멱등성을 끝까지 보존한다 | grounded | `src/quantinue/orchestration/pipeline.py`, `src/quantinue/db/store.py`, 설계서 `#relay` 및 공통 규칙 |
| C4 | 로컬·Docker 설정을 안전하게 분리하고 Quantinue Postgres만 host `5444` / container `db:5432`로 제공한다 | grounded | `compose.yaml`, `.env.example`, 현재 `docker ps` 읽기 결과 |
| C5 | 운영실에서 실행/단계/근거/장애/주문/리뷰 상태를 반응형으로 확인할 수 있게 한다 | grounded | `src/quantinue/main.py`, `src/quantinue/web/` |
| C6 | 설계-파일 매핑 문서와 unit/integration/Docker/responsive test gates로 키 직전 상태를 증명한다 | grounded | `tests/`, `README.md`, `IMPLEMENTATION_ASSUMPTIONS.md` |

## Grounded findings

- 설계서는 1차 MVP를 단일 paper 계좌의 01→11 중복 없는 행복 경로로 제한하며, 2차 기능(다계좌, 멀티턴, 부분체결 완전 처리 등)은 제외한다.
- 현재 `db/schema.sql`은 `pipeline_runs` 한 테이블뿐이고 설계서의 13개 도메인 테이블 및 키/FK/UNIQUE 계약을 구현하지 않는다.
- 현재 역할들은 하나의 `PipelineContext`를 임의 필드로 확장하며 역할별 입력/출력 경계 모델이 없다.
- LLM 인터페이스는 이미 mock/OpenAI/local 분기 초안이 있으나 역할별 시스템 프롬프트가 코드 안에 섞여 있고 evidence/source/time/confidence/version 추적이 없다.
- Alpaca adapter와 `client_order_id` 초안은 있으나 0수량 차단, 동시 재실행 원자성, 제출 전후 체크포인트, 조회 기반 재조정이 없다.
- 현재 Compose DB는 내부 `5432`만 사용하고 host publish가 없다. 계획에서는 오직 이 서비스에 `127.0.0.1:5444:5432`를 추가하며 기존 `localhost:5432` 컨테이너에는 명령이나 변경을 가하지 않는다.
- 저장소 상위 Git 관점에서 `app/` 전체가 untracked로 보인다. 실행자는 이를 사용자 작업물로 보존하고 범위 밖 삭제/초기화/checkout을 금지한다.

## Decisions and defaults

- Python 3.11 + Pydantic v2 + FastAPI + SQLAlchemy async + asyncpg의 기존 스택을 유지한다.
- 기계 정본은 설계서의 지시대로 `db/schema.sql`, `src/quantinue/core/schemas.py` + `ontology.py`, `config/*.yaml`로 둔다. 기존 `contracts.py`는 호환 facade 또는 작은 실행 모델 모듈로 분리해 250 pure LOC 제한을 지킨다.
- 01~04의 외부 무료 데이터 실수집은 API 키 없는 테스트가 네트워크 변동에 종속되지 않도록 provider protocol + deterministic fixture를 기본으로 하고, 설계서가 명시한 공개 공급자 연결점은 별도 adapter로 둔다. MVP acceptance는 offline deterministic path다.
- 05~08은 역할별 prompt 파일을 패키지 리소스로 로드하며 mock/OpenAI/OpenAI-compatible local이 같은 typed request/result protocol을 구현한다.
- 실제 Alpaca는 paper endpoint만 허용하고 `BROKER_MODE=alpaca`, credentials, `TRADING_ENABLED=true`의 삼중 게이트를 통과해야 제출한다. live endpoint는 MVP에서 거부한다.
- 재시도는 외부 네트워크의 transient 오류에만 bounded exponential backoff+jitter를 적용하고, 계약 검증/하드 리스크/4xx에는 재시도하지 않는다. timeout은 역할 및 adapter 설정값으로 관리한다.
- 체크포인트는 실행과 단계 상태를 PostgreSQL에 원자적으로 저장하고 재시작 시 마지막 성공 단계 다음부터 재개한다. 동일 ticker/cycle/investment 및 동일 client order ID는 DB UNIQUE와 broker reconciliation 양쪽에서 중복 제출을 막는다.
- Docker 통합 테스트는 별도 Compose project name/volume과 host 5444를 사용하며 기존 컨테이너를 stop/remove/recreate하지 않는다.
- UI 변경은 Jinja/CSS의 기존 서버 렌더링 방식을 유지하고 1440/1024/768/390px에서 상태/근거 테이블과 오류가 잘리지 않는지 검증한다.
- 테스트는 TDD로 작성한다. 실 OpenAI/Alpaca 테스트는 키가 없으면 명시적으로 skip되고, 키가 있으면 paper-only opt-in marker로 실행된다.

## Scope

### In

- 사용자가 열거한 11개 필수 작업 전부
- 정본 HTML의 확정된 ENUM, 점수/시각/PK/FK/UNIQUE, relay/evidence 계약
- offline mock 완주, local OpenAI-compatible LLM, OpenAI, Alpaca paper adapter
- DB schema initialization/migration-safe bootstrap, operational run/stage checkpoints
- 운영실의 실행 추적 및 장애 가시화

### Out

- 실거래/live Alpaca
- 다계좌, 능동 매도, trailing stop, 멀티턴 Strategist↔Critic, ML 가격 예측
- 외부 공급자의 대규모 실데이터 수집 성능 완성 및 수익성 검증
- 기존 localhost:5432 서비스/컨테이너/볼륨 변경
- 설계 HTML 자체 수정

## Proposed planning approach

1. 정본 HTML에서 01~11 및 공통 ENUM/DDL/relay를 계약 매트릭스로 추출하고 failing contract tests를 먼저 만든다.
2. ontology와 작은 공통 모델 모듈, 전체 DDL/YAML 설정을 구현해 정본 축을 고정한다.
3. provider protocol과 role-specific request/result models를 만든 뒤 01→11을 순서대로 교체하고 prompt를 독립 리소스로 분리한다.
4. run/stage state machine, evidence lineage, retry/timeout/checkpoint/resume/idempotency를 persistence와 orchestrator에 통합한다.
5. OpenAI/local/Alpaca paper adapter를 wire-level fake tests로 검증하고 credential opt-in tests를 준비한다.
6. Compose 5444 isolation, `.env.example`, mapping/operations docs, control-room observability를 완성한다.
7. unit → PostgreSQL integration → API E2E → Docker smoke → responsive visual QA 순으로 최종 검증한다.

## Approval gate

위 범위와 기본 결정을 바탕으로 단일 결정 완결형 실행 계획을 작성한다. 승인은 계획 파일 작성만 허가하며 제품 코드 실행은 이후 별도 `start work` 지시에서 시작한다.
