# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것. (최종 갱신 2026-07-20 후반 — **R8 완료 · 2차 전체 main 병합 · 문서 정본화 3종 · 다음 블록은 웹 2면 W1**)

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 넷을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md          ← 현재 상태 (여기부터, 2026-07-20 후반 현행화됨)
2. docs/mvp2-planning/open-items.md           ← 열린 항목 정본 (막는 작업 없음)
3. docs/mvp2-planning/web-two-sides-plan.md   ← 이번 블록의 계획서 (확정 결정 W-D1~D5)
4. docs/mvp2-planning/future-roadmap.md       ← 의도적으로 미룬 것 — 여기 있는 건 지금 안 만든다

설계 정본은 docs/quantinue-integrated-design.html (v6.0, JOB 12종 기준).
개발기·결함 사전·코드 맵·전체 ERD는 docs/quantinue-engineering.html.
둘 다 코드 기준으로 다시 쓴 것이라 믿어도 된다.

========== 상태 ==========

**재설계는 끝났다.** Phase 1~5 + 잔여 작업 A~E + R8 전부 완료. 구 11단계
러너는 삭제됐고 시스템은 JOB 12종으로 매일 자동으로 돈다(jobs.enabled=true).

기준선: 유닛/웹 523 green · 통합 105 green · ruff clean.
2차 전체가 main에 병합·push됐다(608ed1d, --no-ff). 현재 HEAD는 main.

핵심 확정(redesign §0 · 되묻지 말 것):
- 체결은 로컬 시뮬(MockBroker) + 시세는 실물(Alpaca 마켓데이터) — D1
- 무장 개념 소멸 — mock이 최종 상태다 — D2
- 주기는 전부 config 소유, 기본 일 1회 — D3
- 정규장 전용(D4) · 손절·익절 동시 발동 시 손절 우선(D5) · 매도 = 별도 청산 행(D7)
- 계좌 평가 = 현금 + 보유수량 * 종가 — D8

JOB 등록 순서가 계약이다 (12종):
  유니버스 → 일봉 → 공시 → 뉴스 → 뉴스와이어 → 매크로 → 스크리닝 →
  인사이더채점 → 분석×성향2 → 청산 → 배분

========== 이번 세션: 웹 2면 Phase W1 (인증과 뼈대) ==========

2차의 확정 결정은 "전체 자동화 + 관리자/유저 2면 서비스"다. 자동화는
끝났고 **남은 절반이 웹 2면**이다. 구 M9(관리자 ERP)·M10(유저 포털) 기획을
잡 세계로 번역한 것이 web-two-sides-plan.md이고, 거기 확정 결정 5개가 있다:

- W-D1 인증은 2단계 — 로그인+세션 먼저, TOTP는 R1(페이퍼 전환) 전 게이트로
- W-D2 관제실은 관리자 구역으로 이동. 단 tb_user가 0행이면 열림(부트스트랩)
- W-D3 수동 컨트롤은 "슬롯 재실행" 하나 — 멱등이 체크포인트 재개를 대체한다
- W-D4 SPY 대비는 벤치마크 수집 잡 선행 (tb_benchmark_price는 생산자가 없다)
- W-D5 매니저·투명성 리포트는 lesson 배선 후순위

**착수 규칙(playbook M9 원문): 첫 태스크 = 와이어프레임.** 계획서에 초안이
있으니 그걸 사용자와 확정한 뒤 구현에 들어가라.

W1 태스크:
  W1-1 의존성·해시 (비밀번호 해시 + 세션 서명 — 라이브러리는 착수 시 확정)
  W1-2 tb_user 배선 ← 스키마만 있고 소비자 0이던 테이블의 첫 소비자
  W1-3 로그인/로그아웃 (실패 메시지 균일 — 계정 존재 여부 비노출)
  W1-4 role 가드 (admin/user 구역 + 부트스트랩 예외)
  W1-5 관리자 시드 (scripts/provision_accounts.py 확장)

완료 기준: **라우트 감사 테스트로 "유저 role의 쓰기 엔드포인트 0"을 강제**.
이건 기획의 보안 서사("LLM이 검증 없이 돈에 닿는 경로 0개")의 일부다.

승계된 확정(phase1-decisions — 되묻지 말 것):
  1유저=1계좌 · 셀프 가입 없음(유저 생성은 관리자만) · 유저 화면 read-only ·
  성향 지정도 관리자.

========== 진행 방식 (지금까지와 동일) ==========

- TDD(실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 테스트만 믿지 말고 실제로 돌려볼 것 — **실행에서만 잡힌 결함 통산 20건**.
  화면은 앱을 띄워 HTTP로 확인해라(포트 8020). 결함 15·16의 교훈:
  화면이 원장보다 많이 세거나 없는 분모를 지어내지 않는지 원장과 대조할 것.
- 문턱·주기·한도는 config/pipeline.yaml 소유, 코드 리터럴 금지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋
- 테스트 삭제 규칙: 고정하던 코드와 **함께만** 삭제, 대체 테스트 같은 커밋
- 스키마 바꾸면 4곳 미러(db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML) + 카탈로그 대조
  + 마이그레이션 2회 멱등
- roles/ 등 핵심 코드에 한국어 '왜' 주석(docstring은 영어 한 줄)
- 비밀번호·세션 키는 절대 하드코딩·로그 금지. .env로.

검증:
  cd app-v2
  uv run pytest tests/unit tests/test_pipeline_dashboard.py -q   # → 523 green 기준
  uv run ruff check src tests scripts     # 파이프(| tail) 걸지 말 것 — 종료코드가 가려진다
  통합(105 green)은 일회용 DB — 새 컨테이너에 db/schema.sql 적재 후 1회만.
  -p no:unraisableexception 필요. 같은 컨테이너에서 두 번 못 돌린다
  (멱등 가드가 옛 행을 지켜내 실패를 가린다 — 실제로 밟은 함정).
  포트 5481~5498은 이전 세션 컨테이너가 쓸 수 있으니 빈 것을 골라라.

실 확인 환경:
  QUANTINUE_DATA_MODE=public · QUANTINUE_DATABASE_MODE=postgres · URL은 5445.
  ⚠️ .env의 QUANTINUE_DATABASE_URL은 5444(1차 DB)를 가리킨다. 반드시 5445로
  덮어써라. 안 그러면 다른 작업자의 DB에 쓴다.
  dev DB(5445)에는 실 봉 53만 + 뉴스 1440행 + 잡 실행 기록 + 실 포지션(계좌
  10개) + equity 스냅샷이 들어 있다 — 화면 개발에 쓸 실데이터가 이미 있다.

  LLM이 필요하면 QUANTINUE_LLM_MODE=local (oMLX 127.0.0.1:8888/v1,
  Qwen3.6-35B-A3B-OptiQ-4bit). max_tokens 기본 512. 성향 2종 한 바퀴 ≈ 15분.

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지. git stash 금지.
- 앱 포트 8020(이전 세션 서버가 잡고 있을 수 있다 — 남의 프로세스를 죽이지
  말고 다른 포트를 쓸 것). DB 5445. .env를 .env.example로 덮어쓰지 말 것.
- Alpaca 키는 유효하다(R8 세션 재발급). 단 기동 중 앱은 옛 키를 메모리에
  들고 있으므로 키를 바꾸면 재시작할 것.
- Alpaca 한도는 확정됐다: Basic 무료 데이터·트레이딩 각각 분당 200요청.
  현재 피크는 백필 ~88/분이라 2.3배 여유. 레이트 리미터는 일부러 안 넣었다.
- **push는 사용자 지시가 있을 때만.** 지난 세션에 2차 전체를 main에
  병합·push했다(공유 저장소라 임의 push 금지 원칙은 유지).

와이어프레임 확정하고, 계획 세우고, 시작 전에 한 번 짚어줘.
```
