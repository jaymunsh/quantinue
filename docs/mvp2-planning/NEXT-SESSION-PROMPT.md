# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것.

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md         ← 현재 상태·다음 할 일 (여기부터)
2. docs/mvp2-planning/pipeline-redesign.md   ← 신 실행 정본. 확정 결정 D1~D8 + Phase 1~5 + 착수점 file:line
3. docs/mvp2-planning/future-roadmap.md      ← 의도적으로 미룬 것들 — 여기 있는 건 지금 안 만든다

작업 브랜치는 sunghyuk. 2026-07-19 재설계 확정 — 구 M5~M11은 폐기(playbook은 완료 기록용),
잡 기반 아키텍처로 점진 교체한다. Phase 1a 착수 지점이다.

핵심 확정(redesign §0, 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker 승격) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장(BROKER_MODE=alpaca) 개념 소멸 — 로드맵 R1. mock이 최종 상태다
- 주기는 전부 config 소유, 기본 일 1회. 아키텍처는 실시간형 유지(M1 스케줄러 재사용) — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 점진 교체, 빅뱅 금지(D6)
- 매도 = 별도 청산 행(order_type='close'+closes_order_id) + 자기 sell 시그널 행 — D7

이어서 Phase 1을 진행해라 (상세·file:line은 redesign §4):
- 1a 장부 바닥: sell 회계(입금)·오픈 포지션 판정(closes 조인)·포트폴리오 투영 side 인식·
     Order 계약 확장·캡 order_type 필터·client_order_id 파생 단일화 (a1~a6)
- 1b 시뮬 체결 엔진 승격: 브래킷 발동 판정(일봉 고저, 손절 우선)·close 체결
- 1c 청산 잡: 독립 잡 + M1 스케줄러. 시간 청산(exits.time_exit_bdays 첫 소비)·하드 이벤트.
     soft 논지 붕괴는 Phase 3

진행 방식은 지금까지와 동일하게:
- TDD (실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 문턱·주기·한도는 전부 config/pipeline.yaml 소유, 코드 리터럴 금지
- 계약이 바뀌면 기존 테스트도 같은 커밋에서 갱신
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋에 넣는다
- 스키마를 바꾸면 4곳 전부 반영: db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML(컬럼표+ERD+사전+changelog)
- Phase 완료 시 handoff + 정본 HTML(#logic·changelog) 미러

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 681 green 유지
  uv run ruff check src tests scripts
  통합은 일회용 DB 전제 — 새 컨테이너에 db/schema.sql 적재 후 1회 실행 (63 green)

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지
- 앱 실행 포트 8020, DB 5445
- 재설계 결정 D1~D8·계좌 금액·매도 주문 표현은 확정됨 — 되묻지 말 것
- Alpaca 마켓데이터 엔드포인트·한도는 Phase 2 착수 시 문서로 확인(추정 금지).
  실패 시 폴백 체인 확정됨: Alpaca → Stooq(일봉) → Finnhub(호가) → 기존 public 소스 (redesign §5)
- 테스트는 고정하는 코드와 함께만 삭제, 대체 테스트 같은 커밋 (redesign §3)
- Phase 4 구 러너 삭제는 동등성 증거 보고 + 사용자 확인 후에만 — 유일한 확인 지점

계획 세우고 시작 전에 한 번 짚어줘.
```

---

## 세션 종료 시점 상태 (2026-07-19, 재설계 세션)

| 항목 | 값 |
|---|---|
| 브랜치 | `sunghyuk` |
| 테스트 | 유닛/웹 **681** · 통합 **63** · ruff clean |
| 이번 세션 산출물 | **재설계 정본 확정** — `pipeline-redesign.md`(D1~D8·Phase 1~5) + `future-roadmap.md` 신설, handoff·playbook·본 문서 갱신. 코드 변경 없음 |
| 브로커 | `BROKER_MODE=mock` — **최종 상태**(D1). 무장 개념 소멸, alpaca 키는 로드맵 R1 대비 보존 |
| DB | 5445 (`app-v2-db-1`) · 앱 8020 |
| 정본 HTML | v5.2 — 파이프라인 흐름도는 아직 구 11단계 기준(코드 확정 Phase부터 미러) |

### 재설계 근거 요약 (상세는 redesign §1)

11단계 선형 런의 구조 결함 4가지: 픽 50개를 05~08이 안 읽는 50→1 절벽 · 스케줄 트리거 NVDA 하드코딩(api/schemas.py:18) · "후보 중 뭘 살까"를 묻는 배분 단계 부재 · 재개가 스테이지 수=역할 인덱스 전제(pipeline.py:123)라 팬아웃 불가. 알맹이(판단 규칙·스키마·원장) 7~8할은 재사용, 배관(오케스트레이션)만 교체.

### 이월된 ⏳ (구 playbook §보완 목록 + ghost 감사 — Phase 귀속은 redesign에 반영)

| 항목 | 귀속 |
|---|---|
| `exits.time_exit_bdays` 소비 | Phase 1c |
| `screening.llm_depth` 소비 · `risk_off_action` · conservative 도달 · `skipped_rules` 저장 | Phase 3 |
| `daily_loss_limit` + 당일 시작 equity 스냅샷 | Phase 4 |
| 캡 기본값 4곳 불일치(1/1/1/5) | Phase 4 |
| `budget.daily_llm_usd`·`tb_llm_usage` | 구 M8 — 재설계 후 위치 재판단 |
| `role_05` 공시 신선도 창 | Phase 3 |
| role_11 계좌별 채점 · 이중 캘린더 정리 | Phase 5 전후 |
| `QUANTINUE_HTTP_USER_AGENT` 실제 연락처 | 배포 전 |
