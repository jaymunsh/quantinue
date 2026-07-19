# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것. (최종 갱신 2026-07-20 — **Phase 3 완료 7/7**)

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md         ← 현재 상태·커밋 대응표 (여기부터)
2. docs/mvp2-planning/pipeline-redesign.md   ← 실행 정본. 확정 결정 D1~D8 + Phase 1~5
3. docs/mvp2-planning/future-roadmap.md      ← 의도적으로 미룬 것 — 여기 있는 건 지금 안 만든다

작업 브랜치는 sunghyuk. Phase 1·2·3 전부 완료. 다음은 Phase 4다.

핵심 확정(redesign §0, 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker 승격) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장(BROKER_MODE=alpaca) 개념 소멸 — mock이 최종 상태다 — D2
- 주기는 전부 config 소유, 기본 일 1회. 아키텍처는 실시간형 유지 — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 점진 교체(D6)
- 매도 = 별도 청산 행(order_type='close'+closes_order_id) + 자기 sell 시그널 — D7
- 계좌 평가 = 현금 + 보유수량 * 종가 — D8

이미 끝난 것(다시 만들지 말 것):
- Phase 1 전체 · Phase 2 데이터층·배관·공시
- Phase 3 전부: 성향 정합(2198467) · 일봉 백필(2c8f7b2) · 스크리닝 잡(724ddc2) ·
  분석 잡(b361772) · 상장폐지 보유 이월(29a2e00) · 제약 이름 드리프트(6759083) ·
  페르소나 2종(7dafdc5+57d49c3) · 뉴스 일괄 수집(22ad910) ·
  청산 soft path(4b1dd6a) · 매도 산술 결함 수리(a15b8d8) · 유령 둘 해소(662c626)

잡 등록 순서가 계약이다:
  유니버스 → 일봉 → 공시 → 뉴스 → 스크리닝 → 분석×성향수 → 청산

========== ⚠️ Phase 4 착수 전에 먼저 볼 것 ==========

--- 0. 분석 프롬프트에 지표가 없다 (2026-07-20 실행에서 발견) ---

실 LLM 36건 중 크리틱 승인이 1~2건뿐이다. 반박 내용이 전부 같은 말이다:
"거래량 급증 데이터 누락" · "이평 정렬 부재" · "재무/공시 근거 완전 부재".

원인은 모델이 까다로워서가 아니라 **증거를 안 줬기 때문**이다.
db/domain.py의 rank_universe SQL은 rs_20·ma20/50·vol_ratio·high_252_ratio·rsi를
전부 계산하는데, analysis_prompt에 가는 것은 합성 점수 하나(screening_score)와
종가·고저뿐이다. 그런데 두 페르소나는 오닐(CAN SLIM)·미너비니(SEPA)에 정박돼
있어서 **바로 그 지표들을 요구한다.** 모델이 "근거가 없다"고 쓰고 크리틱이 그걸
근거로 반박하는 자기충돌이다.

고치는 법은 싸다 — 이미 계산된 값을 AnalysisSubject에 실어 프롬프트에 적는다.
새 API 콜 0. 승인이 안 나면 Phase 4 배분 잡에 배분할 후보가 없으므로 먼저 할 것.
고친 뒤 실 LLM으로 승인율을 재측정하고, 두 성향 격차도 다시 볼 것.

--- 0-b. 매크로가 새 경로에 잡으로 없다 ---

domain.latest_macro는 지금 **구 러너 role_04가 쓴 행**을 읽는다. Phase 4에서 구
러너를 지우면 매크로가 끊기고, risk_off_action·macro_penalty_table이 다시 유령이
된다. 배분 잡과 함께 매크로 잡을 세울지 판단할 것.

========== Phase 4 — 배분 잡 + 구 러너 폐기 (redesign §7) ==========

- 후보 집합 **전체**를 계좌별로 놓고 "어느 N개를 살까"를 정하는 신설 단계.
  사이징·리스크 한도는 기존 로직 승계(build_order_plan·_blocking_reason).
- 캡 기본값 4곳 불일치 정리(core/config.py:106 · orchestration/policy.py:102 ·
  role_09/service.py:39 =1 · role_09/contracts.py:33 =5, 실효값은 env=5).
- daily_loss_limit 배선: 당일 시작 equity 스냅샷 tb_account_equity_daily —
  소비자와 같은 커밋. 전제 3개 중 2개는 이미 충족(매도·시가평가).
- 후보 정렬 기준(확신도 단독 vs 리스크 조정)은 착수 시 설계(redesign §10).
- ⚠️ **구 11단계 러너 삭제는 동등성 증거(E2E)를 나에게 보고하고 확인받은 뒤에만.**
  자율 런 중 유일한 확인 지점이다.
- 구 러너를 지우면 conservative 도달 불가 유령(factory.py:50 DEFAULT_PROFILE_NAME)이
  자연소멸한다 — 지금 손대지 말고 그때 확인만 할 것.

그 다음 Phase 5는 redesign §8 그대로(대시보드 잡 기반 · 정본 HTML 흐름도 미러 ·
ghost 재감사 · 이중 캘린더 정리).

========== 판단해야 할 것 (dev-handoff에 상세) ==========

- ensure_holding_in_scope는 유지 판단 그대로. 유니버스 이월은 유니버스 잡이
  성공했을 때, 이 함수는 스크리닝이 실패한 날을 덮는다. 서로 다른 실패를 막는다.
- LOCAL 경로가 retries=0으로 굳어 있다(provider.py:249). 모델이 구조화 출력을
  한 번 놓치면 그 성향 20종목이 통째로 날아간다. openai 전환 시 재확인.
- dev DB(5445)에 매도 측정용 포지션 3건이 열려 있다(TMO·NET·FTNT, 계좌
  TEST-SELLGAP). 필요 없으면 청산 잡이 시간 청산으로 닫는다.

========== 진행 방식 (지금까지와 동일) ==========

- TDD (실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 테스트만 믿지 말고 실제로 돌려볼 것. 지금까지 잡힌 결함 12건이 전부 테스트를
  통과한 뒤 실행에서 나왔다. 가장 최근 것이 12번인데 특히 볼 만하다:
    **상위 랭킹 보유는 산술적으로 팔 수 없었다** — 약세 확신의 분모에 스크리닝
    점수가 섞여 있어서, 픽(정의상 상위)은 모델이 음수를 내야만 팔렸다.
    유닛 테스트는 전부 통과하고 있었다. 실 LLM에 실 포지션을 물려 재보고 나서야
    드러났다.
  잡을 만들면 실 config·실 DB·실 API로 한 틱 돌려봐라
- 문턱·주기·한도는 전부 config/pipeline.yaml 소유, 코드 리터럴 금지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋. **소비자가 도달 가능한지도
  확인할 것** — risk_off_action은 문턱만 고쳤으면 매크로가 안 와서 안 돌았다.
- 스키마를 바꾸면 4곳 전부: db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML.
  그리고 '신규 설치 == 마이그레이션' 카탈로그 대조 + 마이그레이션 2회 멱등 확인.
  대조 방법: 두 DB(신규=app-v2/db/schema.sql · 구세대=app/db/schema.sql 적재 후
  migrations/mvp2.sql)에서 pg_constraint를 뽑아 diff. 지난 세션 156개 완전 일치.
  인덱스(pg_indexes)도 같이 뜨는 것을 확인했다.
- 테스트는 고정하는 코드와 함께만 삭제, 대체 테스트 같은 커밋
- 핵심·에이전트(roles/) 코드에는 '왜'를 설명하는 한국어 인라인 주석
  (docstring은 영어 한 줄)

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 859 green 유지
  uv run ruff check src tests scripts
  통합(118 green)은 일회용 DB 전제 — 새 컨테이너에 db/schema.sql 적재 후 1회만.
  통합은 -p no:unraisableexception이 필요하다(asyncpg GC의 ResourceWarning).
  ⚠️ 통합 테스트는 계정 이름이 고정이라 **한 컨테이너에서 두 번 못 돌린다** —
  재실행하려면 컨테이너를 새로 만들어라.
  포트 5481~5497은 이전 세션 컨테이너가 쓸 수 있으니 비어 있는 것을 골라라.

실 스모크 방법:
  build_job_runner를 실 Settings + JobSources(analyzer=...)로 세우고 잡을 직접
  run(as_of) 한다. 단 잡을 직접 부르면 tb_job_run에 성공 기록이 안 남아
  covered_tickers/스크리닝이 유니버스 스냅샷을 못 찾는다 —
  reserve_job_run + finish_job_run(succeeded=True)을 함께 불러라.

  ⚠️ .env의 QUANTINUE_DATABASE_URL은 **5444(1차 DB)를 가리킨다.** 반드시
  5445로 덮어써라. 안 그러면 다른 작업자의 DB에 쓴다.

  ⚠️ 같은 슬롯을 다시 재려면 먼저 비워라. save_signal은 on_conflict_do_nothing
  (멱등 가드)이라 재실행이 첫 판단을 안 덮어쓴다:
    DELETE FROM tb_critic_verdict v USING tb_strategist_signals s
     WHERE v.signal_id=s.id AND s.trade_date=:d
       AND s.id NOT IN (SELECT signal_id FROM tb_order);
    DELETE FROM tb_strategist_signals s
     WHERE s.trade_date=:d AND s.id NOT IN (SELECT signal_id FROM tb_order);
    DELETE FROM tb_job_run WHERE slot_date=:d AND job_name LIKE 'analysis:%';

  환경: QUANTINUE_DATA_MODE=public · QUANTINUE_DATABASE_MODE=postgres ·
  QUANTINUE_DATABASE_URL은 5445. 개발 DB에는 마이그레이션이 적용돼 있고 실 봉
  53만 개(2026-07-17까지) + 실 뉴스 1440행이 들어 있다 — as_of는 07-20을 쓸 것.

  LLM 검증이 필요하면 QUANTINUE_LLM_MODE=local. oMLX가 127.0.0.1:8888/v1에 떠
  있고 모델은 Qwen3.6-35B-A3B-OptiQ-4bit다. 성향 2종 분석 한 바퀴에 약 4분씩.
  mock 분석기는 STRATEGY 0.76 · CRITIC 0.82 고정이라 성향 격차·크리틱 reject
  갈래는 mock으로 검증 불가능하다.

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지. git stash도 쓰지 말 것
- 앱 실행 포트 8020, DB 5445
- .env를 .env.example로 덮어쓰지 말 것 — Alpaca 키가 날아간다
- Alpaca 분당 호출 한도는 여전히 미확인. 추정해서 박지 말 것.
  (봉: 배치 400종목 OK · 클래스 구분자는 점(BRK.B) · 미지 심볼 1개가 배치 전체를
  죽인다 / 뉴스: limit 상한 50 · 4일 창이 16페이지 767기사 14.5초 — 전부 실측)
- 재설계 결정 D1~D8·계좌 금액·매도 주문 표현은 확정됨 — 되묻지 말 것
- Phase 4 구 러너 삭제는 동등성 증거 보고 + 내 확인 후에만 — 유일한 확인 지점
- push 금지(공유 저장소). 커밋만 쌓을 것
- 끝까지 자율 진행할 것. 심각한 문제가 없으면 중간에 멈추지 말고,
  컨텍스트 한계가 오면 문서 갱신하고 다음 세션 프롬프트를 만들어라

계획 세우고 시작 전에 한 번 짚어줘.
```
