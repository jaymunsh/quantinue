# 다음 세션 시작 프롬프트

> `/clear` 또는 compact 후 아래 블록을 그대로 붙여넣으면 된다.
> 이 파일 자체도 세션 종료 시 갱신할 것.

---

```
Quantinue MVP-2 개발 이어서 진행. 나는 문성혁, app-v2/에서 2차 개발 중이다.

먼저 이 셋을 읽고 현재 상태를 파악해라:
1. docs/mvp2-planning/dev-handoff.md      ← 현재 상태·다음 할 일 (여기부터)
2. docs/mvp2-planning/dev-playbook.md     ← 실행 정본 (마일스톤별 ✅/🔶와 남은 태스크)
3. docs/mvp2-planning/ghost-config-audit.md ← 선언만 되고 소비자 없는 값들. M5·M8 착수 전 필독

작업 브랜치는 sunghyuk. W0~M4·M6 완료, M5 착수 지점이다.
매도 주문 표현은 이미 확정됐다(별도 청산 행, order_type='close' + closes_order_id).

이어서 M5를 진행해라:
- 5-1 분석 대상 ∪ 보유 (팬아웃 생기면 screening.llm_depth도 소비자를 얻는다)
- 5-2 role_07 sell 판단 + 프롬프트 개정(성향 페르소나 2종)
- 5-3 Critic 매도 검증
- 5-4 청산 3층 (브래킷 / 시간 exits.time_exit_bdays / 논지 붕괴)
- 5-5 브로커 청산 (브래킷 leg 취소 → 시장가 매도, close용 client_order_id 파생)
- 5-6 장외 청산 개방 · 5-7 보호주문 상태기계

진행 방식은 지금까지와 동일하게:
- TDD (실패 테스트 → 최소 구현 → green → 태스크 단위 1커밋)
- 문턱·한도는 전부 config/pipeline.yaml 소유, 코드 리터럴 금지
- 계약이 바뀌면 기존 테스트도 같은 커밋에서 갱신
- 새 게이트·외부 연동은 ①유닛 ②통합 ③강제 발동 E2E ④실호출 드라이런까지
- 유령 금지: 새 config 키·DB 컬럼은 소비자와 같은 커밋에 넣는다
- 스키마를 바꾸면 4곳 전부 반영: db/schema.sql · db/migrations/mvp2.sql ·
  tests/integration/schema_sql_expectations.py · 정본 HTML(컬럼표+ERD+사전+changelog)
- 마일스톤 완료 시 playbook + 정본 HTML(#logic·#troubleshooting·changelog) 미러

검증:
  cd app-v2 && uv run pytest tests/unit tests/test_web.py -q   # 681 green 유지
  uv run ruff check src tests scripts
  통합은 일회용 DB 전제 — 새 컨테이너에 db/schema.sql 적재 후 1회 실행 (63 green)

주의:
- app/(1차)은 다른 작업자 WIP — 절대 수정 금지
- 앱 실행 포트 8020, DB 5445
- 거래 세션 정책·계좌 금액·매도 주문 표현은 확정됨 — 되묻지 말 것
- 실 페이퍼 무장(W0-7)은 반드시 내 확인 후에만
- .env는 TRADING_ENABLED=true · BROKER_MODE=mock 상태다(확인됨, 의도된 값).
  즉 BROKER_MODE 한 줄만 alpaca로 바꾸면 실 페이퍼 무장이 완료된다 —
  그 한 줄은 반드시 내 확인 후에만 건드려라

계획 세우고 시작 전에 한 번 짚어줘.
```

---

## 세션 종료 시점 상태 (2026-07-19)

| 항목 | 값 |
|---|---|
| 브랜치 | `sunghyuk` |
| 테스트 | 유닛/웹 **681** · 통합 **63** · ruff clean |
| 워킹트리 | `app-v2/`·`docs/` **깨끗** (`app/` 154개 변경은 다른 작업자 WIP — 불간섭) |
| 정본 HTML | **v5.2** |
| 무장 | `TRADING_ENABLED=true`(확인됨) · **`BROKER_MODE=mock` ← 이 한 줄이 W0-7의 전부** · exposure `90000` · cap `5` |
| DB | 5445 (`app-v2-db-1`), 최신 마이그레이션 적용 완료 |
| 앱 | 8020에 현재 코드로 기동 중 |

### 🔓 무장 상태 — 자물쇠가 하나 남았다

`TRADING_ENABLED=true`는 **의도된 값이다**(2026-07-19 문성혁 확인). 삼중 게이트 중 둘은 이미 열려 있다:

| 잠금 | 상태 |
|---|---|
| `alpaca_base_url` = 페이퍼 엔드포인트 | ✅ 열림(코드가 이 값만 허용 — 실거래 URL이면 앱이 기동조차 안 된다) |
| `TRADING_ENABLED=true` | ✅ 열림 |
| `BROKER_MODE=alpaca` | 🔒 **닫힘** — 현재 `mock` |

**남은 한 줄이 W0-7 무장 전부다.** MockBroker는 `TRADING_ENABLED`를 보지도 않으므로 지금 실주문은 나가지 않는다. 이 한 줄은 **사용자 확인 후에만** 바꾼다.

무장 시 예상 주문 규모: 포지션당 $22,500 · 4건에서 노출 천장($90,000) 도달 · 현금 10% 유지.

### 완료 마일스톤

- **W0** 드라이런 완주 (W0-7 무장·W0-8 스모크만 남음)
- **M1** 슬롯 멱등·NYSE 캘린더·스케줄러 · **M2** 스키마 확장 · **M3** 깔때기 복원
- **M4** 판단 방어선 8건 + 신설 2건 · 검증 라운드(E2E 강제 발동·유령 감사)
- **M6** 계좌 구조 — 6-1 ✅ · 6-2 🔶 3/4 · 6-3 ✅ · 6-4 ✅
- **M5** 매도 주문 표현 확정 (스키마 완료, 로직 미착수)

### 이월된 ⏳ (상세는 playbook §보완 목록)

| 항목 | 조건 |
|---|---|
| `daily_loss_limit` | M5 매도 + 시가평가 + 당일 시작 equity 스냅샷. 판정은 E2E-3 |
| `risk_off_action` | 전제 없음 — role_07에 계좌 프로필이 닿을 때 |
| `budget.daily_llm_usd`·`tb_llm_usage` | M8 |
| `role_05` 공시 신선도 창 | `filings[0]`이 날짜 무관 — 3개월 전 공시가 오늘 시그널이 될 수 있다 |
| `premarket_gap_max` 3% | 잠정값 — `tb_order_plan`으로 발동 횟수 관측 후 보정 |
| 차단매체 LLM 호출 0 | 필터는 동작 확인, 차단 자체는 표본에 없어 미관측 |
| role_11 계좌별 채점 | 현재 대표 계좌만 — M7 리뷰 구조와 함께 |
| `QUANTINUE_HTTP_USER_AGENT` | 배포 전 실제 연락 가능한 주소로 (SEC 공정접근) |
