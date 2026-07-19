# 개발 핸드오프 — 현재 상태

> 최종 갱신 2026-07-19 (재설계 반영). **이 파일은 "지금 어디까지 왔나"만 담는다.**
> 실행 지시는 **`pipeline-redesign.md`**(신 정본)에 있다 — 새 세션은 그 파일을 열고 이어가면 된다.

> 🔁 **다음 세션 시작 프롬프트**: `docs/mvp2-planning/NEXT-SESSION-PROMPT.md` — clear/compact 후 그대로 붙여넣으면 된다.

## ⚠️ 2026-07-19 재설계 — 계획이 바뀌었다

M5 착수 실사에서 구조 결함(50→1 절벽·NVDA 하드코딩 트리거·배분 단계 부재·스테이지 수=역할 인덱스 재개 전제)이 확인되어 **M5~M11 마일스톤 체계를 폐기하고 잡 기반 재설계로 전환**했다. 함께 확정된 결정: **체결은 로컬 시뮬 + 시세는 실물(Alpaca)**, 무장 개념 삭제(로드맵행), 주기는 config 소유·기본 느슨. 전체 결정 D1~D8과 Phase 계획은 `pipeline-redesign.md` §0·§4~8.

## ⭐ 먼저 읽을 것

1. **`pipeline-redesign.md`** — 신 실행 정본. 확정 결정(D1~D8)·진단·Phase 1~5·착수점 file:line.
2. **`future-roadmap.md`** — 의도적으로 미룬 것(페이퍼 전환·장외·인트라데이·스트리밍…)과 각각의 얻는 것/치르는 것.
3. `dev-playbook.md` — **완료 기록**(W0~M4·M6)과 보완 목록은 유효. M5~M11 테이블은 superseded.
4. `ghost-config-audit.md` — 유령 설정 감사(동결 문서). 재설계 Phase별 해소 귀속은 redesign §4~7에 반영됨.
5. `docs/quantinue-integrated-design.html` — 설계 정본 v5.2. ⚠️ 파이프라인 흐름도는 아직 구 11단계 기준 — 코드가 확정되는 Phase부터 미러.
6. `m4-scope-decisions.md` · `troubleshooting-log.md` — 시점 기록(동결).

## 현재 상태 (2026-07-19)

| 항목 | 상태 |
|---|---|
| 작업 브랜치 | **`sunghyuk`** (여기서 계속) |
| main 병합 | Wave 0~1 병합 완료(`818416e`, `--no-ff`). push 보류 — 공유 저장소, 사용자 확인 후 |
| 테스트 | 유닛/웹 **681 green**(2026-07-19 재확인) · 통합 **63 green** · ruff clean |
| DB | app-v2 전용 포트 **5445**(`app-v2-db-1`). 1차 `app-db-1`(5444)은 다른 작업자 WIP — 불간섭 |
| 앱 포트 | **8020** |
| 브로커 | `BROKER_MODE=mock` — **이제 이게 최종 상태다**(D1: 로컬 시뮬 체결). `TRADING_ENABLED=true`·alpaca 키는 페이퍼 전환(로드맵 R1) 대비 보존 |
| 매도 스키마 | ✅ 완료 — `order_type CHECK ('bracket','close')`·`closes_order_id`·조건부 삼중제약(schema.sql:131-149) + DDL 테스트 5건 |

### 완료 (구 마일스톤 체계 기준 — 기록 유효)

- **W0** 드라이런 완주(01→11, HTTP 201) — W0-7/W0-8은 재설계로 소멸(로드맵 R1로 이동)
- **M1** 슬롯 멱등·NYSE 캘린더·스케줄러 → **재설계에서 그대로 재사용**(D3)
- **M2** 스키마 확장 · **M3** 깔때기 복원 · **M4** 판단 방어선 8+2건 → 방어선 로직은 Phase 3~4에서 재사용
- **M6** 계좌 구조 6-1·6-3·6-4 ✅, 6-2 3/4 → 사이징·리스크 한도는 Phase 4 배분 잡이 승계
- **M5** 매도 주문 표현 확정(스키마 완료, 로직은 Phase 1이 담당)

### 다음 할 일

1. **Phase 1a** — 장부 바닥 4곳 + 캡 필터 + 멱등키 단일화 (redesign §4 표 a1~a6, file:line 포함). TDD로 하나씩.
2. **Phase 1b** — 시뮬 체결 엔진 승격(브래킷 발동 판정·손절 우선·close 체결).
3. **Phase 1c** — 청산 잡(시간 청산 `exits.time_exit_bdays` 첫 소비 + 하드 이벤트).
4. 이후 Phase 2(데이터층·Alpaca 시세 어댑터·시가평가) → 3(분석 잡·07 sell) → 4(배분 잡·구 러너 폐기) → 5(정리).

## 확정된 정책 (되묻지 말 것)

- **체결 로컬 시뮬 + 시세 실물** (D1) · **무장 없음, 페이퍼 전환은 로드맵** (D2) · **주기는 config·기본 일 1회** (D3) · **정규장 전용** (D4) · **동시 발동 시 손절 우선** (D5) · **점진 교체** (D6) · **매도 = 별도 청산 행 + sell 시그널** (D7) · **시가평가 = 현금 + 보유×실호가** (D8)
- 계좌 구성(공격 $150K·$100K·$5K / 안전 $100K·$5K + 테스트 2), 거래 세션 정책(전 세션은 로드맵 R2)도 기존 확정 유지.
- `app/`(1차) 절대 수정 금지 · 문턱은 config 소유 · 유령 금지 · 스키마 4곳 미러.

## 실행 명령

```bash
cd app-v2
uv run pytest tests/unit tests/test_web.py -q          # 681 green 유지
uv run ruff check src tests scripts
uv run uvicorn quantinue.main:app --port 8020
docker compose up -d db                                 # 5445

# 통합(63)은 일회용 DB — 새 컨테이너에 db/schema.sql 적재 후 1회
docker run -d --name t -e POSTGRES_DB=quantinue -e POSTGRES_USER=quantinue \
  -e POSTGRES_PASSWORD=quantinue -p 127.0.0.1:5480:5432 postgres:17-alpine
docker exec -i t psql -q -U quantinue -d quantinue < db/schema.sql
QUANTINUE_TEST_DATABASE_URL="postgresql+asyncpg://quantinue:quantinue@127.0.0.1:5480/quantinue" \
  uv run pytest tests/integration -q
```

## app-v2 재생성이 필요할 때 (거의 없음)

```bash
rm -rf app-v2 && mkdir app-v2 \
  && git archive 6163630 app | tar -x --strip-components=1 -C app-v2 \
  && cp app/.env app-v2/.env
```
※ `.omo/`(1차 오케스트레이션 흔적 21MB)는 baseline에서 제외했다 — 다시 넣지 말 것.
