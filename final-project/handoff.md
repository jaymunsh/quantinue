# 촬영 직전 인계 — 2026-07-27 저녁 기준

> 이 문서는 **다음 세션이 촬영부터 이어받기 위한 상태 스냅샷**이다.
> 발표 구성·원고는 `presentation-plan.md`·`slides-content.md`가 정본이고,
> 여기는 "지금 무엇이 준비됐고 다음에 무엇을 하는가"만 적는다.

## 0. 한 줄 요약

**데모 하네스는 촬영 가능 상태다.** 각본 4장면이 이어받기 모드에서 전부
실측 확인됐고, 남은 것은 촬영 → 편집 → 슬라이드 → 리허설이다.

## 1. 지금 떠 있는 것

| 대상 | 상태 | 접속 |
|---|---|---|
| 운영 8020 | 재기동 완료(2026-07-27 저녁), 오늘 잡 14/14 성공 | `admin` / `quantinue-admin` |
| 운영 DB 5445 | 정상. **읽기 전용 금지선** | `docker exec app-v2-db-1 psql -U quantinue -d quantinue` |
| 데모 8022 | 이어받기 모드로 리셋됨, 각본 완주 확인 | `admin`/`quantinue-admin`, `demo`/`qn-demo-user` |
| 데모 DB 5490 | 일회용. 계좌 7개(사용자 6 + 각본 1) | `docker exec qn-demo-db psql -U quantinue -d quantinue` |

⚠️ **데모 admin 비밀번호는 운영 값(`quantinue-admin`)이다.** 이어받기가 운영
계정을 통째로 복사하므로 `QUANTINUE_DEMO_ADMIN_PASSWORD`는 admin에 안 먹는다
(demo 유저에는 먹는다). 운영 시 정리하기로 하고 넘어간 항목.

## 2. 촬영 명령

```bash
cd app-v2
# 촬영 시작 직전에 리셋한다 — 각본이 시간축을 탄다
DEMO_WITH_HISTORY=1 QUANTINUE_DEMO_USER_PASSWORD='qn-demo-user' \
  ./scripts/run_demo.sh reset
./scripts/demo_preflight.sh          # dup_orders=0 dup_fills=0 확인
./scripts/run_demo.sh stop           # 촬영 종료
```

**각본 타이밍** (리셋 시점 기준):
- 즉시: 시드 보유(VRDN 100주 @150, HLXM 200주 @80) + 배경 원장
- ~1분: 사건 재판단 → **NVEX 호재 매수**(S3), **HLXM 악재 반전 매도**(S4)
- ~5분: **VRDN 손절 $139.50**(S2, 5번째 tick)

## 3. 촬영 모드 실측값 (2026-07-27 저녁)

```
일일 리포트: 판단 50건 중 39건 통과, 배분 3건 매수·338건 보류,
             방어선 2건 발동
잡 14개 전부 성공 · 계좌 6개 · LLM 지출 $0.19
주문 34 = 체결 34 (중복 0)
```

각본 4장면 체결 기록:

| 장면 | 종목 | 결과 |
|---|---|---|
| 시드 | VRDN · HLXM | bracket 매수 |
| S3 호재 | NVEX | bracket 매수 $55.00 |
| S4 악재 반전 | HLXM | close 매도 $80.00 (`thesis_soft`) |
| S2 방어선 | VRDN | close 매도 $139.50 (손절) |

## 4. 이번 세션에서 고친 것 (커밋 10개)

**본제품 결함 — 운영 rejudge를 켜면 터질 자리였다**
- `95e0ce5` 판단이 공시 계보에 **판단 시각**을 적어 FK 위반 → 종목이 조용히
  실패 → 그 실패가 tick 전체를 멈춰 재판단 매수·매도가 통째로 안 나갔다.
  계보는 채점 행의 시각(그 슬롯 자정)을 가리켜야 한다. 실패 로그도 추가.

**데모 하네스**
- `c3263ba` 이어받은 운영 픽이 현금을 먼저 써서 각본 주인공이 최소 현금
  문턱에 걸림(픽 점수로 우선순위) + 시드 "시작 보유" 판단이 재판단과 같은
  시각에 앉아 그 종목 재판단이 막힘(1분 앞으로)
- `26ebba4` 검증용 계좌(TEST-*) 4개를 데모 화면에서 제외
- `230f2d8` 매수인데 "판단을 보류한다"고 적히던 문구 모순 해소

**화면 (운영에도 반영됨)**
- `317a01a` 관제실을 일일 리포트로 열고, 보류 수백 건은 접기 (34,760px →
  12,900px)
- `cad0275` 숫자에 단위 ($·주·%·건·개), 확신도 퍼센트화
- `b2eb821` 섹션 앵커를 현재 화면 아래로, 상태 라벨 한글화
- `c595792` 슬롯 바 최근 5일 + 날짜 선택기

**테스트**
- `041c764` 통합군이 포트 충돌로 **아예 안 돌고 있었다**(5490을 데모가 점유).
  runbook 절차로 복구 → 통합 190 green. 그 사이 깨져 있던 기대값 1건 수정.

## 5. 검증 기준선

| 항목 | 값 | 비고 |
|---|---:|---|
| 유닛·웹 | **799** | `pytest tests/unit tests/test_*.py` |
| 통합 | **190** | 아래 절차 필요 (데모와 포트 충돌) |
| Ruff | clean | `ruff check src tests` |

통합 테스트는 **데모를 내리고** 돌려야 한다:

```bash
./scripts/run_demo.sh stop && docker rm -f qn-demo-db
docker run -d --name qn-itest -e POSTGRES_PASSWORD=test-only \
  -e POSTGRES_DB=contracts -p 127.0.0.1:5490:5432 postgres:16
until docker exec qn-itest pg_isready -U postgres -d contracts -q; do sleep 1; done
docker exec -i qn-itest psql -X -q -U postgres -d contracts \
  -c "CREATE ROLE quantinue LOGIN PASSWORD 'quantinue';" \
  -c "CREATE DATABASE quantinue OWNER quantinue;"
docker exec -i qn-itest psql -q -U postgres -d contracts < db/schema.sql
docker exec -i qn-itest psql -q -U quantinue -d quantinue < db/schema.sql
QUANTINUE_TEST_DATABASE_URL="postgresql+asyncpg://quantinue:quantinue@127.0.0.1:5490/quantinue" \
  .venv/bin/python -m pytest tests/integration -q -p no:unraisableexception
docker rm -f qn-itest
```

## 6. 다음에 할 일 (순서대로)

1. **본 촬영** — S1~S5 장면별 원본을 `final-project/footage/`에 저장
   (기존 테이크는 구버전 티커라 폐기됨)
2. **ffmpeg 러프컷** — 자막 포함. DEMO/LIVE 배지 색 구분
3. **발표용 3분 요약본** — 구성은 `presentation-plan.md` §4-2
4. **S6 운영 실증거** — 밤 22:30 KST 이후(정규장 개장) 8020 라이브 녹화.
   읽기 전용
5. **슬라이드 9장** — 원고는 `slides-content.md`에 완성돼 있음, 실제 슬라이드
   파일은 미제작
6. **리허설 1회** — 시간 실측 후 §2 배분 조정

## 7. 알려진 이슈 (촬영에 영향 없음)

- **SEC EDGAR 403**: 운영 로그에 `form.20260727.idx` 403이 반복된다.
  재기동 이전부터 있던 현상이고(819건), 오늘 공시 잡은 07-24 데이터로
  `succeeded`라 원장에는 영향 없다. 원인 미조사.
- **시간축**: 데모 판단이 `14:00 UTC`로 찍힌다. 미국 장중을 재현하는 고정
  시계 때문이며 버그가 아니다. 영상에서 "미국 장중 하루를 재생했다"로 말한다.
- **데모 admin 비밀번호**: §1 참조.
- **`TEST-*` 계좌**: 데모에서는 뺐지만 운영 원장의 주문 62건 중 35건이 그
  계좌 것이다. 발표에서는 "운용 6계좌 + 검증용 4계좌"로 구분해 말한다
  (`presentation-plan.md` §5-1에 반영됨).

## 8. 금지선

- 운영 **8020·5445는 읽기(SELECT/GET)만**. 재기동은 runbook 절차를 따르되
  잡이 `running`이 아닐 때만.
- **push는 지시 전 금지.** 현재 미푸시 커밋 다수.
- `app/`(1차 산출물) 불가침.
