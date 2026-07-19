# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것. (최종 갱신 2026-07-19 — Phase 3 분석 잡까지 완료, 상장폐지 건 §11 추가)

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md         ← 현재 상태·Phase별 커밋 대응표 (여기부터)
2. docs/mvp2-planning/pipeline-redesign.md   ← 실행 정본. 확정 결정 D1~D8 + Phase 1~5
3. docs/mvp2-planning/future-roadmap.md      ← 의도적으로 미룬 것 — 여기 있는 건 지금 안 만든다

작업 브랜치는 sunghyuk. Phase 1·2 완료(뉴스 제외) · **Phase 3는 절반 왔다**.

핵심 확정(redesign §0, 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker 승격) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장(BROKER_MODE=alpaca) 개념 소멸 — mock이 최종 상태다 — D2
- 주기는 전부 config 소유, 기본 일 1회. 아키텍처는 실시간형 유지 — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 점진 교체(D6)
- 매도 = 별도 청산 행(order_type='close'+closes_order_id) + 자기 sell 시그널 — D7
- 계좌 평가 = 현금 + 보유수량 * 종가 — D8

이미 끝난 것(다시 만들지 말 것):
- Phase 1 전체 · Phase 2 데이터층·배관·공시 (dev-handoff 표 참조)
- Phase 3 절반:
  * 2198467 성향(inv_type) 정합 — 원장이 aggressive를 conservative로 거짓
    기록하던 것. 페르소나 팬아웃의 전제였다. 청산 시그널은 진입 시그널의
    성향을 물려받는다.
  * 2c8f7b2 일봉 이력 백필 — 별도 잡이 아니라 수집 잡이 "원장이 아는 마지막
    날 ~ 직전 세션"을 채운다(첫 실행=백필, 이후=증분, 경로 하나).
    실측 536,879봉/43.6초, 2회차 0.7초.
  * 724ddc2 스크리닝 잡 — 전 유니버스 DB 랭킹(SQL 윈도 함수, API 0콜).
    상위 llm_depth ∪ 보유. tb_daily_pick.rank 상한 제거(스키마 4곳 미러 완료).
    실측 1998→373(거래대금 필터)→픽 20, 3.7초.
  * b361772 분석 잡 — 05~08 대체. 범위 전체 순회(50→1 절벽 소멸) · 증거 종합
    1콜 · role_07 sell 개방 + 보유 맥락 · role_08 매도 검증(하드 게이트 방향
    인식) · 5분 SLA를 gates.evidence_max_age_minutes로 이관.

잡 등록 순서가 계약이다:
  유니버스 → 일봉 → 공시 → 스크리닝 → 분석×성향수 → 청산

이어서 진행해라 — **상장폐지 구멍부터, 그다음 Phase 3 잔여 4개**:

0. **상장폐지된 보유를 팔 수 없는 구조** ← 여기부터. redesign **§11**에 선택지
   4개 비교·권고안·착수 시 결정할 것 6개까지 다 적어놨으니 그것부터 읽어라.
   요약: tb_daily_pick → tb_universe FK 때문에 상장 피드에서 빠진 보유는 픽
   행을 못 만들고 → sell 시그널을 못 남기고 → close 주문을 못 만든다. 포지션이
   원장에 열린 채 영구히 남는다. delisting_halt가 겨냥한 바로 그 경우다.
   **방향은 A로 확정(문성혁, 2026-07-19)**: 유니버스 재구축 시 상장 피드 ∪
   현재 보유, 이월분은 컬럼으로 표시. 라벨 없이 union만 하면 그 자체가 다음
   세대의 유령이 된다. 컬럼은 불리언 말고 `listing_status TEXT CHECK IN
   ('listed','held_delisted')` 권장 — 나중에 상태가 늘어도 CHECK만 늘리면 된다.
   보유 이월분은 universe_size 절단 대상에서 **제외**할 것(캡 무관).
   스키마 4곳 미러 + 카탈로그 대조 + 2회 멱등.
   **검증은 반드시 실 포지션으로**: 상장폐지 종목을 보유한 상태를 만들고
   유니버스 재구축 → 스크리닝 → 청산까지 돌려 실제로 팔리는지 볼 것.
   이 결함 자체가 "테스트는 통과하는데 실행에서 막히는" 종류다.

1. **성향 페르소나 2종 (프롬프트)**
   지금 두 성향은 **문턱만** 다르고 프롬프트에는 안 들어간다. 실 실행에서
   aggressive와 conservative의 확신도가 **완전히 동일**하게 나왔다.
   prompts/role_07_strategist.md는 아직 2줄짜리 일반문이다.
   프롬프트 로더는 llm/prompts.py의 _RESOURCE_BY_TASK — 성향별 분기가 없다.
2. **뉴스 일괄 수집** — 소스 확정, 구현만 남았다(2026-07-19 실 API 재확인):
     GET https://data.alpaca.markets/v1beta1/news · start/end RFC3339 · limit
     · next_page_token · 심볼 미지정이면 전 시장 · 기사마다 symbols 배열
     · 우리 자격증명 그대로 200 · 소스 benzinga
     응답 실물: id(정수 PK) · headline · summary · created_at/updated_at · url
   tb_news_raw는 tb_disclosure_raw와 같은 패턴(FK 없음). 어댑터는 alpaca_bars.py
   를, 잡·테스트는 sec_daily_index.py + build_disclosures_job을 그대로 미러.
   **소비자가 분석 잡이므로 원장·어댑터·잡을 분석 잡 수정과 같은 커밋에**
   (지금 job.py의 news_score=None 자리에 실제 증거가 들어간다).
   하드 이벤트는 뉴스가 아니라 SEC 폼이 판정한다 — 헤드라인 키워드로 매도를
   발동시키지 말 것.
3. **청산 3층 soft path → 07 sell 연결** (redesign §4 1c의 미완 항목)
4. **ghost 일괄**: risk_off_action(role_08이 risk_off를 무조건 reject라
   aggressive의 penalty가 무시됨) · conservative 도달 불가(factory.py:50
   하드코딩) · skipped_rules 생성·저장 누락(db/domain.py insert)

그 다음 Phase 4 → 5는 redesign §7~8 그대로.

⚠️ 다음 세션이 판단할 것 (내가 남긴 미해결 3건 — dev-handoff에 상세):
- ensure_holding_in_scope를 **지우지 않았다**(문서는 지우라고 한다).
  지우면 스크리닝 실패한 날 청산이 통째로 막힌다 — 폴백으로 남겼다.
- 매도 경로가 실 실행에서 미발동(열린 포지션 0 + mock 분석기 고정 고점수).
  유닛 6건이 덮지만 **실 포지션 심어서 한 번 돌려볼 것**.
- 제약 이름 드리프트 1건(기존): tb_order close 타깃 CHECK가 신규설치
  tb_order_check1 / 마이그레이션 tb_order_close_target_check. 정의는 동일.

진행 방식은 지금까지와 동일하게:
- TDD (실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 테스트만 믿지 말고 실제로 돌려볼 것. 지금까지 잡힌 결함 **10건이 전부**
  테스트를 통과한 뒤 실행에서 나왔다. 최근 3건:
    원장이 성향을 거짓 기록 · 백필 2회차가 30만 봉 재수신 ·
    범위 저장이 평일마다 FK 위반으로 스크리닝 전체를 죽임(주말이라 안 드러남)
  잡을 만들면 실 config·실 DB·실 API로 한 틱 돌려봐라
- 문턱·주기·한도는 전부 config/pipeline.yaml 소유, 코드 리터럴 금지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋에
- 스키마를 바꾸면 4곳 전부: db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML.
  그리고 '신규 설치 == 마이그레이션' 카탈로그 대조 + 마이그레이션 2회 멱등 확인
  (대조 방법: 두 DB에서 pg_constraint를 뽑아 diff. 지난 세션엔 제약 154개 일치)
- 테스트는 고정하는 코드와 함께만 삭제, 대체 테스트 같은 커밋
- 핵심·에이전트(roles/) 코드에는 '왜'를 설명하는 한국어 인라인 주석
  (docstring은 영어 한 줄 — 기존 관행)

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 803 green 유지
  uv run ruff check src tests scripts
  통합(109 green)은 일회용 DB 전제 — 새 컨테이너에 db/schema.sql 적재 후 1회만.
  통합은 -p no:unraisableexception이 필요하다: asyncpg 연결 GC의 ResourceWarning이
  에러로 승격돼 가짜 실패가 뜬다(로직 실패 아님).
  포트 5481~5497은 이전 세션 컨테이너가 쓸 수 있으니 비어 있는 것을 골라라.
  통합 테스트는 전용 계좌(broker_account_id)를 쓸 것 — 기본 계좌
  quantinue-local-simulated는 다른 테스트가 현금 잔고를 정확히 단언하는 공용 자원

실 스모크 방법(지난 세션에서 쓴 그대로):
  build_job_runner를 실 Settings + JobSources(market_data=..., analyzer=...)로
  세우고 잡을 직접 run(as_of) 한다. 단 잡을 직접 부르면 tb_job_run에 성공
  기록이 안 남아 covered_tickers/스크리닝이 유니버스 스냅샷을 못 찾는다 —
  reserve_job_run + finish_job_run(succeeded=True)을 함께 불러라.
  DATA_MODE=public · DATABASE_MODE=postgres · DATABASE_URL은 5445.
  개발 DB(5445)에는 마이그레이션이 적용돼 있고 실 봉 53만 개가 들어 있다.

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지. git stash도 쓰지 말 것
  (stash가 app/까지 삼킨다)
- 앱 실행 포트 8020, DB 5445
- .env는 Alpaca 키가 채워져 있다(2026-07-19 문성혁 직접 입력, 실 200 확인).
  .env를 .env.example로 덮어쓰지 말 것 — 키가 날아간다. 실제로 한 번 날아갔다.
- Alpaca 분당 호출 한도는 여전히 미확인. 추정해서 박지 말 것.
  (배치 400종목 OK · 클래스 구분자는 점(BRK.B) · 미지 심볼 1개가 배치 전체를
  죽인다 · 창 요청은 start/end 한 쌍으로 260일도 요청 수는 하루치와 같다
  — 전부 실측이고 어댑터에 반영돼 있다)
- 재설계 결정 D1~D8·계좌 금액·매도 주문 표현은 확정됨 — 되묻지 말 것
- Phase 4 구 러너 삭제는 동등성 증거 보고 + 내 확인 후에만 — 유일한 확인 지점
- push 금지(공유 저장소). 커밋만 쌓을 것
- 끝까지 자율 진행할 것. 심각한 문제가 없으면 중간에 멈추지 말고,
  컨텍스트 한계가 오면 문서 갱신하고 다음 세션 프롬프트를 만들어라

계획 세우고 시작 전에 한 번 짚어줘.
```
