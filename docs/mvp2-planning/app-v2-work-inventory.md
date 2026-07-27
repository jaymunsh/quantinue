# Quantinue MVP-2 app-v2 작업 인벤토리

> 작성일: 2026-07-27 KST  
> 대상: 다음 개발 에이전트와 리뷰어  
> 범위: `0ef30ad` 이후 현재 `HEAD(2d6c8b9)`까지의 `app-v2/` 중심 개발과 관련 문서
>
> 이 문서는 **무엇을 왜 만들었고 어디에 있는지 설명하는 색인**이다. 개발 방향은
> `intraday-realignment.md`, 최신 운영 상태는 `dev-handoff.md` 맨 위 배너,
> 실행·검증 명령은 `operations-runbook.md`가 정본이다. 이 문서와 정본이
> 충돌하면 정본을 따른다.

---

## 1. 한눈에 보는 개요

Quantinue MVP-2는 실물 시장 데이터(Alpaca)와 OpenAI 판단을 사용하지만 실제
브로커 주문은 내지 않는 **모의 자동매매 시스템**이다. 일일 체인이 종목을
발굴하고, 장중 감시 층이 보유 종목과 당일 후보를 추적하며, 중요한 가격 변화나
뉴스·공시 사건이 생겼을 때 전략가와 critic이 다시 판단한다. 체결은
`MockBroker`가 로컬 원장에 모의로 기록한다.

이번 작업의 핵심은 기존의 “거래일마다 한 번”인 일일 체인을 없애는 것이 아니라
그 위에 다음 두 층을 추가한 것이다.

1. **결정론적 방어층**: 정규장 중 1분마다 가격을 확인하고 손절·익절을 즉시
   모의 체결한다. 이 경로는 LLM을 호출하지 않는다.
2. **장중 판단층**: ±5% 가격 이동, 뉴스·공시 사건, 뉴욕 시각 정기 스윕에서만
   전략가와 critic을 호출해 매수·매도 판단을 갱신한다.

따라서 현재 구조는 다음과 같다.

```text
일일 체인
  시장 데이터 → 스크리닝 → 전략가 → critic → 배분 → 모의 주문·체결
       │
       └─ 보유 종목 + 당일 후보
                    │
장중 감시(1분) ────┼─ 손절·익절 → 즉시 모의 청산
                    ├─ ±5% 가격 사건
뉴스·공시 사건 ────┤
정기 스윕 3회 ─────┘
                         ↓
                장중 전략가 → critic
                         ↓
                 기존 청산·배분 경로
```

## 2. 사용자 확정 원칙

- 실제 브로커 주문은 하지 않는다. `MockBroker` 기반 페이퍼 체결이 최종 범위다.
- 시세·뉴스·공시는 실물 데이터를 사용할 수 있다.
- 새 종목 발굴은 거래 슬롯당 한 번이지만, 방어와 기존 종목의 판단 갱신은
  장중에 수행한다.
- 방어는 1분 결정론 루프, LLM은 사건과 제한된 정기 스윕에서만 호출한다.
- 모든 LLM 호출은 `BudgetedAnalyzer`와 일일 비용 상한을 통과한다.
- 화면 시각은 KST, DB 원장은 UTC, 거래 슬롯 날짜는 뉴욕 날짜다.
- 문턱·주기·한도·요율은 `app-v2/config/pipeline.yaml`이 소유한다.
- 운영 앱은 8020, 개발 앱은 8021 + mock LLM, DB는 반드시 5445다.
- `app/`은 다른 작업자의 WIP이므로 수정하지 않는다.
- push는 사용자 지시가 있을 때만 한다.

장중 재판단 초기 운영값은 다음과 같이 확정됐다.

| 항목 | 값 |
|---|---:|
| 가격 이동 트리거 | 직전 종가 대비 ±5% |
| 종목별 재판단 쿨다운 | 30분 |
| 정기 스윕 | 뉴욕 10:00 / 12:45 / 15:15 |
| 매도성 재판단 예산 예약 | 일일 예산의 20% |

## 3. 구현 완료 범위

### 3-1. 장중 감시 M1~M7

`intraday-realignment.md` §9의 M1~M7은 코드와 테스트가 완료됐다.

| 단계 | 구현 내용 | 핵심 파일 |
|---|---|---|
| M1 | `WatchConfig`, 정규장 게이트, disabled no-op 감시 러너 | `orchestration/policy.py`, `watch_runner.py` |
| M2 | Alpaca 최신 체결가 배치 조회와 fixture 시세 | `market_data/alpaca_quotes.py`, `fixture.py` |
| M3 | 브래킷 손절·익절을 장중 현재가로 평가하고 같은 tick에 청산 | `watch_runner.py`, `roles/exits/` |
| M4 | ±5% 트리거, 30분 쿨다운, 전략가·critic 재사용, 매도 예산 예약 | `intraday_rejudge.py`, `llm/budget.py` |
| M5 | 하루 3회 정기 스윕과 기존 `AllocationJob` 기반 장중 매수 | `intraday_rejudge.py`, `roles/allocation/job.py` |
| M6 | 관제실 장중 감시·재판단 카드 | `api/pipeline_*`, `web/templates/pipeline.html` |
| M7 | 보유 종목 웹소켓 + 전체 대상 1분 polling 하이브리드 | `alpaca_stream.py`, `watch_factory.py` |

웹소켓은 실계정에서 30종목 구독 성공, 31번째 한도 오류를 확인했다. 그래서
보유 종목만 최대 30개 스트리밍하고 당일 후보와 초과분은 계속 1분 폴링한다.
스트림이 끊겨도 폴링 방어는 유지된다.

### 3-2. 뉴스·공시 사건 기반 재판단

`app-v2/src/quantinue/events/` 패키지를 새로 추가했다.

- 뉴스·공시 증분 수집과 커서 관리
- 시장 세션 수집 가드
- 사건 정규화와 안정적인 중복 제거 키
- 원문 provenance 및 저장 불변성
- 보유 종목·당일 후보 교집합 라우팅
- 원문 근거 묶음과 긴 문서 요약 캐시
- 전략가와 critic의 persona별 재판단
- 원자적 호출 예약과 at-most-once 경계
- uncertain 상태를 포함한 재시작 안전성
- 변경된 판단을 기존 청산·배분 경로에 연결
- source별 수집·실패 상태를 관제실에 표시

신규 모듈:

```text
app-v2/src/quantinue/events/
├── __init__.py
├── adapters.py
├── analysis.py
├── analysis_repository.py
├── evidence.py
├── evidence_repository.py
├── execution.py
├── ingestion.py
├── repository_queries.py
├── routing.py
├── routing_repository.py
└── runtime.py
```

### 3-3. LLM 비용과 동시성 보호

- 동시에 여러 판단이 시작돼도 일일 예산 예약이 직렬화된다.
- 호출 전에 모델별 최대 예상 비용을 예약해 hard cap을 넘지 않는다.
- 공급자가 usage를 누락하면 최대 예상 비용으로 보수적으로 기록한다.
- 모델 요율은 `pipeline.yaml`에 선언해야 하며 미선언 유료 모델은 기동을
  거부한다.
- 모든 일일·장중 판단은 동일한 `BudgetedAnalyzer` 경계를 통과한다.
- 일반 판단이 예산의 80%를 사용하면 매수성 판단을 막고, 남은 20%는 보유
  종목의 매도성 재판단에 예약한다. 전체 일일 상한 자체는 넘지 않는다.

관련 파일:

```text
app-v2/src/quantinue/llm/
├── budget.py
├── provider.py
├── provider_factory.py
├── transport.py
└── usage_limits.py
```

### 3-4. 운영 안정화

- 8020 운영 owner와 8021 web-only 개발 인스턴스를 분리했다.
- owner lock에 PID뿐 아니라 프로세스 시작 identity를 기록한다.
- 개발 인스턴스는 `BACKGROUND_WORKERS=0`으로 자동 잡·감시·알림을 차단한다.
- 감시·스트림·폴링·작업 owner의 실제 런타임 상태를 노출한다.
- 취소된 감시 작업을 장애로 오인하지 않는다.
- Healthchecks.io heartbeat가 앱·DB·worker 침묵을 외부에서 감시한다.
- heartbeat 오류는 앱 lifespan과 일일 체인을 쓰러뜨리지 않는다.
- DB 포트 5445 계약을 셸 테스트로 고정했다.
- 계좌 시가평가 결과를 센트 단위 `ROUND_HALF_UP`으로 확정했다.

관련 파일:

```text
app-v2/scripts/run_observation.sh
app-v2/scripts/test_compose_contract.sh
app-v2/src/quantinue/core/config.py
app-v2/src/quantinue/core/logging.py
app-v2/src/quantinue/notify/heartbeat.py
app-v2/src/quantinue/notify/telegram.py
app-v2/src/quantinue/runtime_status.py
```

### 3-5. 관제실과 사용자 화면

- 잡 체인을 실제 실행 순서와 상태 레일로 정리했다.
- 장중 감시, poll/stream 상태, 사건 수집 및 재판단 상태를 표시한다.
- 실제 sell fill이 있는 방어선 발동 내역을 표시한다.
- SPY 일봉을 수집하고 `/me`에서 계좌 수익률과 비교한다.
- 사용자 계좌 평가액과 시간 표시를 정합화했다.
- 화면의 운영 숫자는 설정값을 추측하지 않고 DB 원장으로 답할 수 있는 것만
  표시한다.

관련 파일:

```text
app-v2/src/quantinue/api/
├── my_account.py
├── pipeline_day.py
├── pipeline_presentation.py
└── schedule.py

app-v2/src/quantinue/web/
├── static/dashboard.css
└── templates/
    ├── login.html
    ├── me.html
    ├── pipeline.html
    └── schedule.html
```

## 4. 주요 코드 변경 파일 지도

### 새로 추가된 운영 코드

```text
app-v2/src/quantinue/events/                       # 사건 수집·근거·라우팅·재판단
app-v2/src/quantinue/llm/provider_factory.py
app-v2/src/quantinue/llm/transport.py
app-v2/src/quantinue/llm/usage_limits.py
app-v2/src/quantinue/market_data/alpaca_quotes.py
app-v2/src/quantinue/market_data/alpaca_stream.py
app-v2/src/quantinue/notify/heartbeat.py
app-v2/src/quantinue/orchestration/benchmark_job.py
app-v2/src/quantinue/orchestration/intraday_rejudge.py
app-v2/src/quantinue/orchestration/watch_factory.py
app-v2/src/quantinue/orchestration/watch_policy.py
app-v2/src/quantinue/orchestration/watch_runner.py
app-v2/src/quantinue/orchestration/work_lease.py
app-v2/src/quantinue/roles/exits/alerts.py
app-v2/src/quantinue/runtime_status.py
```

### 주요 수정 코드

```text
app-v2/config/pipeline.yaml
app-v2/db/schema.sql
app-v2/db/migrations/mvp2.sql
app-v2/src/quantinue/main.py
app-v2/src/quantinue/db/domain.py
app-v2/src/quantinue/db/domain_records.py
app-v2/src/quantinue/llm/budget.py
app-v2/src/quantinue/llm/provider.py
app-v2/src/quantinue/orchestration/job_factory.py
app-v2/src/quantinue/orchestration/job_runner.py
app-v2/src/quantinue/orchestration/policy.py
app-v2/src/quantinue/roles/allocation/job.py
app-v2/src/quantinue/roles/analysis/job.py
app-v2/src/quantinue/roles/exits/contracts.py
app-v2/src/quantinue/roles/exits/job.py
```

## 5. 테스트 자산

기능 구현은 TDD로 진행했고 단위·웹·통합·셸 테스트를 함께 추가했다.

### 장중 감시와 운영

```text
app-v2/tests/unit/test_watch_runner.py
app-v2/tests/unit/test_watch_policy.py
app-v2/tests/unit/test_alpaca_quotes.py
app-v2/tests/unit/test_alpaca_trade_stream.py
app-v2/tests/unit/test_intraday_rejudge.py
app-v2/tests/unit/test_benchmark_job.py
app-v2/tests/unit/test_runtime_status.py
app-v2/tests/unit/test_runtime_ownership.py
app-v2/tests/unit/test_heartbeat.py
app-v2/tests/integration/test_watch_sweep_ledger.py
app-v2/tests/shell/test_run_observation.sh
app-v2/tests/shell/test_run_observation_process_tree.sh
```

### 사건 파이프라인

```text
app-v2/tests/unit/test_event_analysis.py
app-v2/tests/unit/test_event_decision_execution.py
app-v2/tests/unit/test_event_evidence.py
app-v2/tests/unit/test_event_ingestion_config.py
app-v2/tests/unit/test_event_ingestion_runtime.py
app-v2/tests/unit/test_event_routing.py
app-v2/tests/unit/test_event_runtime_session_gate.py
app-v2/tests/unit/test_event_source_adapters.py
app-v2/tests/integration/test_event_analysis_production_seam.py
app-v2/tests/integration/test_event_evidence.py
app-v2/tests/integration/test_event_routing.py
app-v2/tests/integration/test_event_storage_contract.py
app-v2/tests/integration/test_event_storage_migration.py
app-v2/tests/integration/test_event_storage_provenance.py
app-v2/tests/integration/test_event_trigger_arbitration.py
app-v2/tests/integration/test_incremental_event_ingestion.py
```

### LLM과 DB 회귀

```text
app-v2/tests/unit/test_llm_budget.py
app-v2/tests/unit/test_llm_budget_hard_cap.py
app-v2/tests/unit/test_llm_budget_missing_usage.py
app-v2/tests/unit/test_llm_provider.py
app-v2/tests/integration/test_account_valuation.py
app-v2/tests/integration/test_allocation_job.py
```

최신 인수인계에 기록된 검증 기준선은 유닛·웹 729개, 통합 112개, Ruff
clean이다. 이 숫자는 이후 테스트 추가에 따라 달라질 수 있으므로 다음
에이전트는 개수 자체보다 명령의 성공 여부를 확인한다.

## 6. 관련 문서 지도

### 반드시 먼저 읽을 정본

| 문서 | 역할 |
|---|---|
| `NEXT-SESSION-PROMPT.md` | 금지선, 환경, 포트, DB, 진행 규칙 |
| `intraday-realignment.md` | “하루 1회” 재정렬과 M1~M7 설계 정본 |
| `dev-handoff.md` | 최신 구현·운영 상태. 맨 위 배너가 우선 |
| `operations-runbook.md` | 기동·관측·종료·통합 검증 명령 |
| `open-items.md` | 아직 닫히지 않은 운영 및 후속 항목 |

### 이번 범위에서 작성·현행화한 문서

```text
docs/mvp2-planning/NEXT-SESSION-PROMPT.md
docs/mvp2-planning/completion-plan.md
docs/mvp2-planning/dev-handoff.md
docs/mvp2-planning/intraday-event-reassessment-plan.md
docs/mvp2-planning/intraday-realignment.md
docs/mvp2-planning/open-items.md
docs/mvp2-planning/project-status-and-roadmap.md
docs/operations-runbook.md
docs/quantinue-day-anatomy.html
docs/quantinue-engineering.html
docs/quantinue-integrated-design.html
docs/weekly-report-fist-week.md
docs/weekly-report-second-week.md
app-v2/README.md
app-v2/DESIGN.md
```

`docs/quantinue-day-anatomy.html`은 실제 하루를 따라가며 전체 흐름을 이해할 때
가장 빠른 보조 자료다.

## 7. 구현 완료와 운영 활성 상태의 차이

코드가 존재하는 것과 8020 운영 인스턴스에서 켜진 것은 다르다.

최신 정본에 기록된 8020 상태:

```text
broker=mock
llm=openai
watch=true
rejudge=false
stream=false
DB=127.0.0.1:5445
```

- `watch=true`: 1분 polling과 결정론적 방어는 운영 활성 상태다.
- `rejudge=false`: 사건·가격·정기 스윕의 유료 장중 LLM 재판단은 구현됐지만
  운영에서는 아직 꺼져 있다.
- `stream=false`: 보유 종목 웹소켓은 구현됐지만 마지막 운영 관문 전까지
  꺼져 있다.

순차 활성화 원칙은 다음과 같다.

```text
clean OpenAI 일일 슬롯 검증
  → rejudge Gate B
  → 기능일 및 다음 거래일 안정성 확인
  → stream 활성화
  → 연결·fallback·롤백 확인
```

## 8. 시연 영상 준비 상태

시연 영상 계획 문서는 작성됐지만, 영상용 독립 데모 하네스는 아직 구현되지
않았다.

작성된 계획:

- `docs/mvp2-planning/demo-video-plan.md`
- `.omo/plans/quantinue-demo-video.md` (`.omo/`는 Git ignore 대상)

계획의 목적은 실제 시장 사건을 기다리지 않고도 운영 환경과 격리된
결정론적 데모에서 다음 흐름을 재현하는 것이다.

```text
초기 계좌
  → 가격 급락과 브래킷 방어
  → 호재 사건과 매수 재판단
  → 악재 사건과 매도 반전
  → 중복 주문 0 / 무사건 LLM 0콜
  → 운영 8020의 읽기 전용 실증거
```

아직 구현되지 않은 데모 구성:

```text
app-v2/src/quantinue/demo/
app-v2/scripts/run_demo.sh
포트 8022 + 일회용 DB 5490 런타임
각본 시세 소스와 고정 시계
시나리오 mock LLM
각본 사건 소스
데모 전용 seed와 reset
촬영 preflight
S1~S6 시나리오 계약과 리허설
```

따라서 **MVP-2 본제품 개발 완료**와 **영상용 데모 하네스 완료**를 혼동하면
안 된다. 전자는 구현됐고 순차 운영 활성화 중이며, 후자는 계획만 확정된 상태다.

## 9. Git 기준과 현재 작업 트리

작업 범위를 Git으로 재현하려면 다음 기준을 사용한다.

```text
기준 부모: 0ef30ad
장중 재정렬 시작: 413deb6 / 9e2633f / d0e8b1b
현재 HEAD: 2d6c8b9
현재 브랜치: main
```

2026-07-27 확인 시 `main`은 `origin/main`보다 55개 커밋 앞서 있으며 push되지
않았다. `0ef30ad..HEAD` 전체에는 merge를 포함해 95개 커밋이 있고,
`app-v2/`를 건드린 커밋은 62개, `docs/`를 건드린 커밋은 34개다.

현재 미커밋 파일:

```text
 M docs/operations-runbook.md
?? docs/mvp2-planning/demo-video-plan.md
?? docs/mvp2-planning/app-v2-work-inventory.md   # 이 문서
```

`operations-runbook.md`의 미커밋 변경은 2026-07-27 09:31 KST에 추가된
인터넷·와이파이 복구 점검 절차다. 작성 주체를 Git만으로 특정할 수 없으므로
다른 변경과 섞어 커밋하지 않는다.

## 10. 다음 에이전트 착수 체크리스트

1. `NEXT-SESSION-PROMPT.md` → `intraday-realignment.md` →
   `dev-handoff.md` → `operations-runbook.md` 순서로 읽는다.
2. `git status --short`로 사용자 미커밋 변경을 보존한다.
3. 8020과 DB 5445에는 운영 정본이 허용한 읽기 전용 확인만 수행한다.
4. 개발 서버가 필요하면 8021, `LLM_MODE=mock`,
   `BACKGROUND_WORKERS=0`으로 실행한다.
5. M1~M7이나 사건 파이프라인을 다시 만들지 않는다.
6. 운영 활성 상태는 YAML만 보지 말고 `/api/runtime/status`, 관제실,
   DB 원장으로 확인한다.
7. 코드 변경은 실패 테스트부터 시작하고 관련 테스트와 Ruff를 통과시킨다.
8. 통합 테스트는 포트 5490의 새 일회용 PostgreSQL에서 한 번만 실행한다.
9. 커밋 전 `./app-v2/scripts/scan_secrets.sh`를 실행한다.
10. 사용자 지시 전에는 push하지 않는다.

## 11. 검증 명령 포인터

정확한 최신 명령은 `operations-runbook.md` §5가 정본이다. 요약하면:

```bash
cd app-v2
uv run pytest \
  tests/unit \
  tests/test_pipeline_dashboard.py \
  tests/test_my_account.py -q
uv run ruff check src tests scripts
./scripts/scan_secrets.sh
```

통합 테스트는 운영 DB 5445가 아니라 포트 5490의 일회용 DB를 사용한다.
`.env`의 `QUANTINUE_DATABASE_URL`은 다른 작업자의 5444를 가리킬 수 있으므로
명령마다 명시적으로 올바른 URL을 사용한다.

---

## 결론

현재 `app-v2/`에는 일일 종목 발굴, OpenAI 전략가·critic, 예산 통제,
MockBroker 체결, 1분 장중 방어, 사건·정기 재판단, 장중 매수·매도,
웹소켓/polling 하이브리드, 관제실과 외부 heartbeat까지 구현돼 있다.

남은 핵심은 기존 기능을 다시 개발하는 것이 아니라 다음 두 갈래다.

1. clean 운영 증거를 쌓으며 `rejudge`와 `stream`을 순서대로 활성화한다.
2. 촬영이 필요하면 운영과 완전히 격리된 결정론적 데모 하네스를 구현한다.

