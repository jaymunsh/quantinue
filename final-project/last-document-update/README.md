# docs/ HTML 문서 갱신 — 요청서

> 작성: 2026-07-27 밤 · **이 작업은 발표 준비와 분리된 별도 세션이다.**
> 발표 준비(영상·슬라이드)는 `final-project/NEXT.md`가 따로 관리한다.
> 섞지 말 것 — 성격이 다르다.

## 이렇게 부르면 된다

> `final-project/last-document-update/README.md` 읽고 진행해.

## 대상

| 문서 | 규모 | 기준일 |
|---|---:|---|
| `docs/quantinue-integrated-design.html` | 2,202줄 · 본문 ~108k자 | 2026-07-24 |
| `docs/quantinue-engineering.html` | 896줄 · 본문 ~46k자 | 2026-07-24 |
| `docs/quantinue-day-anatomy.html` | 366줄 · 본문 ~19k자 | 2026-07-24 |

셋 다 **설계·엔지니어링 기록**이지 현황판이 아니다. 이 구분이 이 작업의
핵심이다 — 현황판으로 착각하고 숫자를 전부 최신화하면 기록이 훼손된다.

## 전제 — 07-27 세션은 앱 코드를 바꾸지 않았다

07-27에는 발표용 촬영·편집·슬라이드만 했다. `app-v2/` 소스는 한 줄도
건드리지 않았으므로 **설계 서술 자체는 여전히 유효하다.** 갱신이 필요한
것은 실측 숫자와 일부 낡은 서술뿐이다.

---

## 고쳐야 할 것 (07-27 스캔에서 확인)

### 1. `day-anatomy` — "안전형 계좌 3개"

```
4. 사이징 — 안전형 계좌 3개에 각각 계획이 선다
```

실측(2026-07-27 운영 5445):

| 성향 | 상태 | 수 |
|---|---|---:|
| 공격형 | active | 3 |
| 공격형 | paused | 1 |
| 안전형 | active | 2 |

→ 운용 6계좌(활성 5 + 일시정지 1) + 회귀 검증용 `TEST-*` 4 = **등록 10**.
"안전형 계좌 3개"는 **활성 2개**로 고친다. 일시정지된
`DEMO-CONSERVATIVE-09`는 이름과 달리 `inv_type`이 **공격형**이라
성향별로 셀 때 헷갈리는 자리다 — 문서에 한 줄 주석을 남기면 좋다.

### 2. 세 문서 공통 — 기준일 07-24 이후 슬롯

07-27 슬롯이 쌓였다. 실측 숫자를 갱신하려면 아래 쿼리를 쓴다
(`presentation-plan.md` §5-3과 같은 쿼리, **읽기 전용**):

```bash
docker exec -i app-v2-db-1 psql -X -U quantinue -d quantinue -P pager=off <<'SQL'
SELECT min(slot_date), max(slot_date), count(DISTINCT slot_date) FROM tb_job_run;
SELECT side, count(*) FROM tb_strategist_signals GROUP BY 1;
SELECT decision, count(*) FROM tb_critic_verdict GROUP BY 1;
SELECT decided_layer, count(*) FROM tb_critic_verdict GROUP BY 1;
SELECT called_at::date, count(*), round(sum(est_cost_usd),4) FROM tb_llm_usage GROUP BY 1 ORDER BY 1;
SELECT count(*) total, count(prompt_version) has_prov FROM tb_strategist_signals;
SQL
```

2026-07-27 실측값(대조용):

```
후보 222 · 판단 342(매수 266/보류 49/매도 27) · 검토 323(통과 222/반려 57/보류 44)
critic 경로: 게이트 271(83.9%) / LLM 52(16.1%)
prompt_version 234 / 342   ← 07-21부터 기록 시작
주문 62 = 체결 62 (운용 27 + 검증용 TEST-* 35)
뉴스 10,728 + 공시 8,973 · LLM 4일 $0.53
```

⚠️ **발표 당일(07-29) 재조회와 묶어서 하면 두 번 일하지 않는다.**

---

## 고치면 안 되는 것 (07-27에 확인함)

### 1. `engineering`의 "판단 91건"

```
14  T+5 리뷰가 잡 판단을 하나도 못 봄 — pipeline_runs 내부 조인은 구 러너만
    채움. 실 DB에서 잡 판단 91건 중 매칭 0건.
```

이건 현재 통계가 아니라 **버그 이력표의 당시 관측값**이다. 최신 숫자로
갱신하면 "그때 무엇을 봤는가"라는 기록의 값이 사라진다. 건드리지 않는다.
같은 표의 다른 행들도 마찬가지다.

### 2. `integrated-design`의 `policy_version` · `input_hash` · `prompt_version`

전부 **스키마 컬럼 정의표**의 항목이다(`policy_version TEXT (계보) 정책
(config) 버전`). "이 컬럼이 있다"는 서술이지 "채워진다"는 주장이 아니므로
틀리지 않았다.

다만 사실 하나는 알아둘 것: **`policy_version`은 342건 전부 비어 있다.**
컬럼은 있는데 아무도 안 채운다. 문서를 고칠 필요는 없지만, "계보를 남긴다"는
서술 근처에 실제 채움률을 한 줄 붙이면 정직해진다:

```
prompt_version · input_hash · model_name : 234 / 342 (07-21부터 기록)
policy_version : 0 / 342 (컬럼만 존재)
```

---

## 교차 확인 — 두 문서가 같은 사건을 말한다

`engineering` 버그 이력 **15번**:

```
15  관제실이 원장보다 많이 셈 — "28건 중 8승인" vs 원장 "22건 분석".
    자정 cycle_ts 필터 부재로 구 러너 행·실험 행 혼입
```

이것이 `control_room_reads.judgements()`의 `cycle_ts = 자정` 필터가 생긴
유래다. 같은 불변식을 `presentation-plan.md` §4-4도 설명한다
("각본 티커가 판단과 반박에 안 뜨는 이유 — 버그가 아니다").

**문서를 고칠 때 이 둘을 어긋나게 하지 말 것.** 하나를 고치면 다른 하나도
같이 본다.

---

## 금지선

- 운영 **8020·5445는 읽기(SELECT/GET)만**
- **push는 지시 전 금지**
- `app/`(1차 산출물) 불가침
- 버그 이력표의 과거 관측값을 최신 숫자로 덮어쓰지 말 것 (위 참조)
