# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것.

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md         ← 현재 상태·Phase별 커밋 대응표 (여기부터)
2. docs/mvp2-planning/pipeline-redesign.md   ← 실행 정본. 확정 결정 D1~D8 + Phase 1~5
3. docs/mvp2-planning/future-roadmap.md      ← 의도적으로 미룬 것 — 여기 있는 건 지금 안 만든다

작업 브랜치는 sunghyuk. 2026-07-19 재설계 확정 후 Phase 1 완료 · Phase 2 3/5 진행.
Phase 2 잔여부터 이어간다.

핵심 확정(redesign §0, 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker 승격) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장(BROKER_MODE=alpaca) 개념 소멸 — 로드맵 R1. mock이 최종 상태다
- 주기는 전부 config 소유, 기본 일 1회. 아키텍처는 실시간형 유지 — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 점진 교체(D6)
- 매도 = 별도 청산 행(order_type='close'+closes_order_id) + 자기 sell 시그널 — D7
- 계좌 평가 = 현금 + 보유수량 * 종가 — D8

이미 끝난 것(다시 만들지 말 것):
- Phase 1 전체 — 장부 바닥 6곳 · 시뮬 체결 엔진(브래킷 발동 판정) · 청산 3층 잡
- Phase 2 — tb_daily_bar 원장 + exit_observations 투영 · Alpaca 배치 일봉 어댑터
  (src/quantinue/market_data/alpaca_bars.py) · 계좌 시가평가(revalue_accounts)

이어서 Phase 2 잔여 → Phase 3~5를 진행해라:
- Phase 2 잔여: ① 유니버스 주간 실배선(선언은 원래 weekly —
  role_01_universe_screener/contracts.py:62 — 코드만 매 런이었다)
  ② 뉴스·공시 일괄 수집(종목별 폴링 → 그날 피드 통째로 받아 종목 매칭).
  공시 하드 이벤트가 붙으면 청산 잡의 DailyObservation.has_hard_event가 채워진다
- Phase 3: 스크리닝 잡(tb_daily_bar 기반 DB 랭킹, 전 유니버스) → 상위
  screening.llm_depth(20) ∪ 보유 → 분석 잡(종목별 LLM 2~3콜) ·
  role_07 sell 개방 + 보유 맥락 + 성향 페르소나 2종 · role_08 매도 검증
- Phase 4: 배분 잡(후보 전체 × 계좌별 선택+사이징) → 구 11단계 러너 폐기
- Phase 5: 대시보드 잡 상태 기반 · 정본 HTML 미러 · ghost 재감사

진행 방식은 지금까지와 동일하게:
- TDD (실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 문턱·주기·한도는 전부 config/pipeline.yaml 소유, 코드 리터럴 금지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋에
- 스키마를 바꾸면 4곳 전부: db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML.
  그리고 '신규 설치 == 마이그레이션' 제약 정의 비교 + 마이그레이션 2회 멱등 확인
- 테스트는 고정하는 코드와 함께만 삭제, 대체 테스트 같은 커밋
- 핵심·에이전트(roles/) 코드에는 '왜'를 설명하는 한국어 인라인 주석
  (docstring은 영어 한 줄 — 기존 관행)

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 721 green 유지
  uv run ruff check src tests scripts
  통합(82 green)은 일회용 DB 전제 — 새 컨테이너에 db/schema.sql 적재 후 1회만.
  같은 DB에 두 번 돌리면 중복키로 실패하는 게 정상이다.
  통합 테스트는 전용 계좌(broker_account_id)를 쓸 것 — 기본 계좌
  quantinue-local-simulated는 다른 테스트가 현금 잔고를 정확히 단언하는 공용 자원

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지. git stash도 쓰지 말 것
  (stash가 app/까지 삼킨다 — 이번 세션에서 실제로 겪음)
- 앱 실행 포트 8020, DB 5445
- 재설계 결정 D1~D8·계좌 금액·매도 주문 표현은 확정됨 — 되묻지 말 것
- Alpaca 분당 호출 한도는 공식 문서에 없다. 추정해서 박지 말 것
- Phase 4 구 러너 삭제는 동등성 증거 보고 + 내 확인 후에만 — 유일한 확인 지점
- push 금지(공유 저장소). 커밋만 쌓을 것

계획 세우고 시작 전에 한 번 짚어줘.
```

---

## 세션 종료 시점 상태 (2026-07-19, Phase 1 완료 + Phase 2 3/5)

| 항목 | 값 |
|---|---|
| 브랜치 | `sunghyuk` (push 안 함) |
| 테스트 | 유닛/웹 **721** · 통합 **82** · ruff clean (재설계 착수 기준선 681/63) |
| 마지막 커밋 | `742a87f` 코드 · `1104943` 문서 |
| 브로커 | `BROKER_MODE=mock` — **최종 상태**(D1). 무장 개념 소멸 |
| DB | 5445 (`app-v2-db-1`) · 앱 8020 |
| 정본 HTML | v5.2 — ⚠️ **아직 구 11단계 파이프라인 기준.** Phase 5에서 미러 |
| `app/` | 154개 변경 그대로 — 무손상 확인 |

### Phase 1 완료 — 시스템이 팔 줄 안다

통합 테스트로 왕복 확인: 매수 체결 → 손절 발동 → sell 시그널 → close 주문 → 매도 체결 → 현금 +170 → 보유 0.

문서에 적어둔 결함 6건이 **전부 실패 테스트로 재현된 뒤** 수리됨 — 상세·커밋 대응표는 `dev-handoff.md`.

### Phase 2 진행 3/5

✅ `tb_daily_bar` 원장 + `exit_observations` 투영 · Alpaca 배치 어댑터(500콜 → 1~2콜) · 계좌 시가평가(D8)
⏳ 유니버스 주간 실배선 · 뉴스·공시 일괄 수집

### 이어받는 사람이 알아야 할 임시 조치 1건

**`domain.ensure_holding_in_scope()`는 Phase 3이 넘겨받아야 한다.** `tb_strategist_signals`가 `(trade_date, ticker) → tb_daily_pick`을 참조하는데, 스크리너에서 탈락한 보유 종목은 청산 시그널을 남길 자리가 없었다. 재설계의 "상위 N ∪ 보유"가 스키마 제약으로 드러난 것이라, 청산 잡이 임시로 `bucket='backfill'` 픽을 만들어 계보를 잇는다. **Phase 3 스크리닝 잡이 보유를 정식으로 범위에 넣으면 이 함수는 사라진다.**

### 이월된 ⏳

| 항목 | 귀속 |
|---|---|
| `screening.llm_depth` 소비 · `risk_off_action` · conservative 도달 · `skipped_rules` 저장 · `role_05` 공시 신선도 창 | Phase 3 |
| `daily_loss_limit` — 전제 3개 중 **2개 충족**(매도 ✅ · 시가평가 ✅), 남은 것은 당일 시작 equity 스냅샷 | Phase 4 |
| 캡 기본값 4곳 불일치(config 1 / policy 1 / service 1 / contracts 5, 실효값 env=5) | Phase 4 |
| Alpaca 분당 호출 한도 실측 · `budget.daily_llm_usd`·`tb_llm_usage` | 미정 / 구 M8 |
| role_11 계좌별 채점 · 이중 캘린더 정리(role_11 자체 → `core/market_calendar`) | Phase 5 전후 |
| `QUANTINUE_HTTP_USER_AGENT` 실제 연락처 | 배포 전 |
