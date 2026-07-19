# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것. (최종 갱신 2026-07-20 심야 — **Phase 4 완료 + 구 러너 삭제 승인 완료**)

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md         ← 현재 상태·커밋 대응표 (여기부터)
2. docs/mvp2-planning/pipeline-redesign.md   ← 실행 정본. 확정 결정 D1~D8 + Phase 1~5
3. docs/mvp2-planning/future-roadmap.md      ← 의도적으로 미룬 것 — 여기 있는 건 지금 안 만든다

작업 브랜치는 sunghyuk. Phase 1~4 전부 완료. 이번 세션은 Phase 5다:
대시보드 잡 기반 전환 → 구 러너 삭제 → 정리. 끝까지 자율 진행해라.

핵심 확정(redesign §0, 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker 승격) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장(BROKER_MODE=alpaca) 개념 소멸 — mock이 최종 상태다 — D2
- 주기는 전부 config 소유, 기본 일 1회. 아키텍처는 실시간형 유지 — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 점진 교체(D6)
- 매도 = 별도 청산 행(order_type='close'+closes_order_id) + 자기 sell 시그널 — D7
- 계좌 평가 = 현금 + 보유수량 * 종가 — D8 (배분 잡이 프로덕션 소비자)

⚠️ **구 러너 삭제는 이미 승인됐다** (2026-07-20 문성혁, dev-handoff "결정 패킷"
참조). 되묻지 마라. 합의된 순서: **대시보드를 잡 기반으로 먼저 바꾸고, 그 다음
러너를 지운다** — 지금 지우면 관제실이 빈 화면이 되기 때문이다.

이미 끝난 것(다시 만들지 말 것):
- Phase 1~3 전체(핸드오프 참조) + 승인율 수리(0/22 → agg 8 · cons 3)
- Phase 4 전부: max_tokens A/B 실측→512 확정 · 매크로 잡 · buy 후보 리더 ·
  배분 잡 + tb_account_equity_daily + daily_loss_limit 배선 · 캡 4곳 정리
- 실 스모크: 잡 8종 전부 succeeded (2026-07-20, dev DB) — 배분 33 bought/24
  skipped, 계좌별 게이트 발동 전부 설계 그대로(핸드오프의 표)

잡 등록 순서가 계약이다:
  유니버스 → 일봉 → 공시 → 뉴스 → 매크로 → 스크리닝 → 분석×성향수 → 청산 → 배분

========== Phase 5 작업 순서 ==========

1. **대시보드 잡 기반 전환.** 재료는 원장에 다 있다: tb_job_run(잡 상태·detail) ·
   tb_order_plan(배분 판단·스킵 사유) · tb_account_equity_daily(계좌 곡선) ·
   tb_strategist_signals×tb_critic_verdict(판단·반박). 관제실이 "오늘 파이프라인이
   무엇을 했나"를 잡 체인 기준으로 보여주면 구 러너 화면을 대체한다.

2. **구 러너 삭제.** 배선만 지우고 새 경로가 공유하는 계약은 남긴다:
   - 지운다: CycleScheduler · LiveRunRuntime · /runs API · orchestration/
     pipeline.py·factory.py의 11단계 조립 · roles의 **service**들(01·02·03·04·
     05·06·07·08·09·10·11) 중 소비자가 러너뿐인 것 · config mvp 블록
   - 남긴다(새 경로가 쓴다): role_01 contracts(EvidenceBoundInput·Universe*) ·
     role_04 contracts(regime_from_rate·MacroAnalysisOutput·MVP_BASELINE_*) ·
     role_07/08 contracts(분석 잡) · role_09 contracts(build_order_plan — 배분 잡)
   - 삭제 전 소비자 전수 grep으로 확인할 것(유령 금지의 역방향).
   - 테스트는 고정하던 코드와 함께만 삭제, 대체 테스트 같은 커밋.
   - 자연소멸 확인: factory.py DEFAULT_PROFILE_NAME 유령 · config mvp 블록
     (mvp2.allocation과 값 중복 과도기 해소) · .env DAILY_NEW_ORDER_CAP=1(구 러너
     전용이었다 — 러너가 죽으면 소비자 없는 env가 된다, 정리 판단할 것)

3. **정리(redesign §8 잔여).** 정본 HTML 파이프라인 흐름도를 잡 체인 기준으로
   미러(#logic·changelog) · ghost 재감사(선언·소비자 전수) · 이중 캘린더
   (role_11 자체 캘린더 → core/market_calendar, role_11 삭제로 자연소멸일 수
   있으니 삭제 뒤에 확인) · mvp2.jobs.enabled 켤지 사용자에게 마지막에 제안만.

========== 진행 방식 (지금까지와 동일) ==========

- TDD(실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 테스트만 믿지 말고 실제로 돌려볼 것 — 실행에서만 잡힌 결함 통산 13건.
  대시보드는 실제로 앱을 띄워 브라우저/HTTP로 확인해라(포트 8020).
- 문턱·주기·한도는 config/pipeline.yaml 소유, 코드 리터럴 금지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋
- 스키마 바꾸면 4곳 미러(db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML) + 카탈로그 대조
  (현재 제약 159·인덱스 48 완전 일치) + 마이그레이션 2회 멱등
- roles/ 코드에 한국어 '왜' 주석(docstring은 영어 한 줄)

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 878 green 기준
  uv run ruff check src tests scripts
  통합(127 green)은 일회용 DB — 새 컨테이너에 db/schema.sql 적재 후 1회만.
  -p no:unraisableexception 필요. 같은 컨테이너에서 두 번 못 돌린다.
  포트 5481~5497은 이전 세션 컨테이너가 쓸 수 있으니 빈 것을 골라라.
  ⚠️ 러너 삭제 커밋 뒤에는 유닛 개수가 크게 줄 것이다 — 그 자체는 정상이지만,
  지운 테스트마다 "고정하던 코드가 같이 죽었는가"를 커밋 메시지에 남겨라.

실 스모크 방법:
  build_job_runner를 실 Settings + JobSources(market_data=…, macro=…,
  analyzer=…)로 세우고 잡을 직접 run(as_of) 한다. reserve_job_run +
  finish_job_run(succeeded=True)을 함께 부를 것. 슬롯 재측정 전 비우기 SQL은
  dev-handoff 참조.

  ⚠️ .env의 QUANTINUE_DATABASE_URL은 5444(1차 DB)를 가리킨다. 반드시 5445로
  덮어써라. 안 그러면 다른 작업자의 DB에 쓴다.

  환경: QUANTINUE_DATA_MODE=public · QUANTINUE_DATABASE_MODE=postgres ·
  URL은 5445. dev DB에는 마이그레이션 적용됨(tb_account_equity_daily 포함),
  실 봉 53만(2026-07-17까지) + 뉴스 1440행 + 2026-07-20 잡 8종 성공 기록 +
  배분이 산 실 포지션 33건(계좌 9개)이 들어 있다.

  LLM 검증은 QUANTINUE_LLM_MODE=local (oMLX 127.0.0.1:8888/v1,
  Qwen3.6-35B-A3B-OptiQ-4bit). max_tokens 기본 512(실측 근거).
  성향 2종 한 바퀴 ≈ 12분. mock 분석기는 고정 점수라 성향 격차 검증 불가.

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지. git stash 금지.
- 앱 포트 8020, DB 5445 · .env를 .env.example로 덮어쓰지 말 것(Alpaca 키)
- Alpaca 분당 한도는 여전히 미확인 — 추정해 박지 말 것
- push 금지(공유 저장소). 커밋만 쌓을 것
- 끝까지 자율 진행. 삭제 승인은 이미 받았으니 중간 확인 지점이 없다 —
  심각한 문제가 없으면 멈추지 말고, 컨텍스트 한계가 오면 문서 갱신하고
  다음 세션 프롬프트를 만들어라.

계획 세우고 시작 전에 한 번 짚어줘.
```
