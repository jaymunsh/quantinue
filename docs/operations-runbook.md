# 운영 매뉴얼 — 켜고, 보고, 끄는 법

> 서버 없이 맥 한 대에서 사람이 켜고 끄는 운용을 전제로 쓴다.
> **이 문서만 보고 처음부터 띄울 수 있어야 한다.** 안 되면 그건 문서 결함이다.
>
> 코드·설계 문서는 `docs/mvp2-planning/`에 있다. 여기는 **운영만** 다룬다.

---

## 0. 한 줄 요약

```bash
cd ~/Documents/ClaudeCode/quantinue-v2/app-v2
docker start app-v2-db-1          # DB (이미 떠 있으면 생략)
./scripts/run_observation.sh      # 앱
```

브라우저에서 **http://127.0.0.1:8020/admin** → `admin` / `quantinue-admin`

끝이다. 나머지는 이 셋을 풀어 쓴 것이다.

---

## 1. 켜기

### 1-1. DB 먼저

앱보다 DB가 먼저 떠 있어야 한다. 안 떠 있으면 앱이 기동 중에 죽는다.

```bash
docker start app-v2-db-1
docker ps --format '{{.Names}}\t{{.Ports}}' | grep app-v2-db
# 기대: app-v2-db-1   127.0.0.1:5445->5432/tcp
```

⚠️ **포트 5445가 맞는지 꼭 본다.** `app-db-1`(5444)은 1차 개발용이고 **다른
작업자 것**이다. 거기에 쓰면 남의 데이터를 건드린다.

### 1-2. 앱

```bash
cd ~/Documents/ClaudeCode/quantinue-v2/app-v2
./scripts/run_observation.sh
```

터미널을 계속 열어둬야 한다. 닫으면 앱이 죽는다. 백그라운드로 두려면:

```bash
nohup ./scripts/run_observation.sh > /dev/null 2>&1 &
```

로그는 `app-v2/observation.log`에 쌓인다. 실시간으로 보려면 `tail -f observation.log`.

이 스크립트만 `QUANTINUE_BACKGROUND_WORKERS=1`을 설정한다. 동시에 두 번
실행하면 두 번째 프로세스는 uvicorn을 띄우기 전에 실패한다. 소유권은 이 맥의
`app-v2/.runtime/observation-owner.lock`에만 적용되는 로컬 단일 실행 보장이다.
정상 종료하면 잠금이 지워지고, 기록된 PID가 더 이상 없을 때만 다음 실행이
오래된 잠금을 복구한다.

### 1-3. 떴는지 확인

```bash
curl -s http://127.0.0.1:8020/health
# 기대: {"status":"ok","broker_mode":"mock","llm_mode":"openai"}   (2026-07-21 전환)
```

`llm_mode` 세 가지: **`openai`**가 관측 표준이다(gpt-5.4-mini, `.env`의
`OPENAI_API_KEY` 필요, 비용 ~$0.05/일 수준 예상 — 관제실 LLM 지출 카드로
확인). `local`은 oMLX(127.0.0.1:8888)가 떠 있어야 하는 구 방식. `mock`은
고정값이라 가볍지만 판단이 가짜다 — **코드 작업(8021)용이지 관측용이 아니다.**

⚠️ LLM 쪽이 죽어 있으면(키 오류·oMLX 부재) 분석 잡만 실패하고 나머지는
정상으로 돈다(그리고 텔레그램으로 알림이 온다).

---

## 2. 매일 보기

### 2-1. 가만히 있어도 텔레그램이 온다

| 언제 | 무엇 |
|---|---|
| 잡이 실패한 즉시 | `❌ news 실패 · 슬롯 2026-07-21` |
| 평일 **KST 13:20 전후** | `✅ 2026-07-21 슬롯 · 잡 12/12 성공 · 신규 매수 3건` |

**평일 오후에 아무것도 안 오면 그게 신호다** — 앱이 안 떴거나 맥이 꺼져
있었다는 뜻이다. 알림을 보내는 주체가 앱이라, 앱이 죽으면 침묵한다.

주말·공휴일엔 안 온다. 거래일이 아니면 잡 자체가 안 돈다. **정상이다.**

### 2-1-1. 앱이 죽어서 텔레그램도 못 보내는 경우

앱 안의 실패 알림은 앱이 살아 있어야 보낼 수 있다. 맥 절전·와이파이 단절·
Docker 종료·8020 종료는 **Healthchecks.io 외부 heartbeat**가 맡는다. 운영
`.env`에 `QUANTINUE_HEARTBEAT_URL`이 있으면 8020 단일 작업 소유자만 5분마다
신호를 보낸다. 8021 web-only는 같은 `.env`를 읽어도 heartbeat를 만들지 않는다.

성공 신호는 단순히 HTTP가 열렸다는 뜻이 아니다. DB 5445가 읽히고, 일일 잡과
WatchRunner가 붙어 있으며, 장중 감시가 `attention`이 아닐 때만 보낸다. 그 밖은
`/fail`, 프로세스·맥·네트워크가 완전히 죽으면 신호 자체가 끊긴다.

Healthchecks.io 설정은 check 이름 `quantinue-runtime-8020`, Period 5분,
Grace Time 5분을 쓴다. 호스팅판은 Telegram 전용 integration 대신 **Webhook**으로
기존 Quantinue Telegram bot의 `sendMessage`를 호출하며, Down과 Up(복구) 요청을
각각 켜 둔다. Webhook URL의 bot token, 본문의 chat ID, heartbeat ping URL은 모두
비밀번호와 같으므로 채팅·스크린샷·로그·문서에 붙이지 않고 설정 화면과 `.env`에만
둔다. 2026-07-23 실제 success ping과 외부 화면 `Up`, Webhook 연결까지 확인했다.
관제실 정상인데 외부에서 Down이면 `observation.log`의
`heartbeat.send.failed`와 인터넷 연결부터 본다.

설정 후 확인할 것은 네 가지다.

1. 최근 Events가 약 5분 간격 `OK`인가
2. Current Status가 `Up`인가
3. Schedule이 Period 5분 / Grace Time 5분인가
4. Notification Methods에서 이메일과 Telegram Webhook이 `ON`인가

시각이 KST 13:00인 이유: 슬롯은 **뉴욕 날짜** 기준이고 뉴욕 자정이 KST
13:00이다. 일일 안내는 체인 맨 끝이라 앞의 잡 12개가 끝난 뒤에 온다
(실 LLM 분석이 15분쯤 걸린다).

### 2-2. 직접 볼 때

| 화면 | 링크 | 무엇을 보나 |
|---|---|---|
| 관제실 | http://127.0.0.1:8020/admin | 잡 체인이 **어디서 끊겼나** · 계좌 총람 |
| 계좌 관리 | http://127.0.0.1:8020/admin/accounts | 개설 · 성향 · 정지 |
| 내 계좌 | http://127.0.0.1:8020/me | 유저가 보는 화면 |

관제실에서 볼 것 셋: ① 잡 13개가 다 `succeeded`인가(아니면 화면이 처음 끊긴
잡을 지목한다) ② 슬롯 탭으로 빠진 날이 있는가 ③ 계좌 총람에서 체결이 느는가.

### 2-3. 계정

| 역할 | 볼 수 있는 것 |
|---|---|
| 관리자 | 관제실 · 계좌 관리 (`/me`는 404가 정상 — 계좌가 없다) |
| 일반 사용자 | 자기 계좌만 (`/admin`은 404가 정상) |

아이디와 비밀번호는 로컬 비밀 저장소에서 확인한다. 문서·로그·스크린샷에는
자격 증명을 적지 않는다.

새 계정은 **화면에서** 만든다 — `/admin/accounts` 하단의 계좌 개설 폼.
셀프 가입은 없다.

---

## 3. 끄기

```bash
pkill -f "uvicorn quantinue.main:app"
```

⚠️ **끄기 전에 잡이 도는 중인지 본다.** 도는 중에 끄면 그 슬롯이 `running`
으로 굳고, 재시도는 `failed`만 집으므로 **그 잡은 그날 영영 안 돈다.**

관제실 잡 체인에서 `running` 상태가 있는지 보면 된다. 있으면 끝날 때까지
기다리거나, 껐다면 아래 4-1로 푼다.

DB는 굳이 안 꺼도 된다(유휴 시 CPU 0%·메모리 200MB). 끄려면
`docker stop app-v2-db-1`.

---

## 4. 문제가 생겼을 때

### 4-1. 잡이 `running`에서 안 넘어간다

앱을 잡 도중에 끈 흔적이다. **관제실에서 그 잡 옆의 `잠금 해제` 버튼을 누른다.**
버튼은 잡을 실행하지 않고 잠금만 푼다 — 러너가 다음 틱(최대 60초)에 스스로
다시 집는다.

### 4-2. 텔레그램이 안 온다

1. 앱이 떠 있나 — `curl -s http://127.0.0.1:8020/health`
2. 키가 들어 있나 — `app-v2/.env`의 `QUANTINUE_TELEGRAM_BOT_TOKEN`·`_CHAT_ID`.
   **둘 중 하나라도 비면 알림 경로 자체가 안 만들어진다**(의도된 동작).
3. 오늘 이미 보냈나 — 일일 안내는 하루 한 번이다. 관제실 잡 체인에
   `daily_summary`가 `succeeded`면 이미 갔다.

### 4-3. 한 화면만 500이 난다 (다른 화면은 멀쩡)

**템플릿과 파이썬 코드의 버전이 어긋난 것이다.** 원인은 둘의 반영 시점이
다르기 때문이다:

| | 실행 중인 앱에 언제 반영되나 |
|---|---|
| 템플릿(`.html`) | **즉시** — Jinja가 파일이 바뀌면 다시 읽는다 |
| 파이썬 코드 | 재기동해야 |
| CSS | 재기동해야 (import 시점에 인라인된다) |

그래서 템플릿이 **새 필드**를 참조하는데 코드가 옛것이면 그 화면만 죽는다.
실제로 밟았다(2026-07-21): 작동 로그 템플릿에 쪽 나누기(`total_pages`)를
넣자 관측 인스턴스가 그 필드 없는 옛 모델로 렌더하다 500.

```
tail -40 app-v2/observation.log | grep -A 3 UndefinedError
# jinja2.exceptions.UndefinedError: ... has no attribute 'total_pages'
```

**고치는 법은 재기동뿐이다.** 잡이 도는 중이 아닌지 확인하고 §1-2대로 다시 띄운다.
⚠️ 코드를 고치는 동안 관측 인스턴스가 이 상태에 빠질 수 있다 — 템플릿을
고쳤으면 관측 인스턴스도 그날 안에 재기동할 것.

### 4-4. 화면이 안 열린다 / 로그인이 안 된다

- **포트를 먼저 본다**: `lsof -nP -iTCP:8020 -sTCP:LISTEN`
- 세션 쿠키가 꼬였으면 브라우저에서 로그아웃 후 다시 로그인
- `tb_user`에 행이 있어 관제실은 **로그인을 요구한다**. 예고된 동작이다.

### 4-5. 하루가 통째로 비었다

맥이 꺼져 있었을 가능성이 높다. **그날 안에 앱을 켜면 밀린 잡이 뒤늦게 돈다** —
주기 판정이 요일이 아니라 "마지막 성공으로부터 경과일"이라 그렇다. 뉴욕 날짜
기준이라 창이 넓다(KST 대략 13시 ~ 다음날 13시).

### 4-6. 장중 감시·실시간 스트림을 켤 때

현재 HEAD의 정본 설정은 **`watch=true`, `rejudge=false`, `stream=false`**다.
값은 `.env`가 아니라 `config/pipeline.yaml`의 `mvp2.watch`가 소유한다.
이는 재기동 후보 설정이지, 이미 실행 중인 8020이 `watch=true`를 로드했다는
증거가 아니다. 적용 여부는 설정값이 아니라 관제실의 owner 부착·최근 tick과
`tb_watch_sweep`/관련 실행 원장으로 확인한다.

1. `watch=true`, `rejudge=false`, `stream=false`로 정규장 ready 2회를 확인한다.
2. 깨끗한 8020-only 일일 슬롯과 예산 여유를 확인한 뒤 rejudge만 켠다.
3. poll과 rejudge가 정상인 것을 본 뒤 stream을 마지막으로 켠다.
4. 설정 변경은 실행 중인 앱에 자동 반영되지 않는다. 잡 `running`이 0인지 보고
   한 번만 재기동한다.

무료 계정은 2026-07-22 실측으로 **30종목까지**, 31번째부터 한도 오류였다.
그래서 스트림은 보유 종목만 최대 30개 구독하고, 오늘의 픽과 초과분은 계속
1분 폴링한다. 웹소켓이 끊겨도 이 폴링은 멈추지 않는다. 연결 하나를 이미 다른
프로그램이 쓰고 있다면 인증·연결 오류가 반복될 수 있으므로, 별도 Alpaca
스트림 클라이언트를 동시에 띄우지 않는다.

### 4-6-1. 등록 잡 14종 — 순서·주기·실패 경계

`JobRunner`는 60초마다 “무엇이 due인가”만 확인한다. 실제 실행은 뉴욕 슬롯과
`tb_job_run(job_name, slot_date)` 예약이 막으므로 `universe`는 7일에 한 번,
나머지는 거래 슬롯당 한 번이다. 아래 순서가 데이터 의존성 계약이다.

| 순서 | 원장 이름 | 주기 | 하는 일 | 실패하면 |
|---:|---|---|---|---|
| 1 | `universe` | 7일 | NASDAQ 보통주 세계와 보유 종목을 합쳐 유니버스 스냅샷 저장 | 직전 성공 스냅샷은 남지만 새 주간 세계가 갱신되지 않는다 |
| 2 | `daily_bars` | 1일 | 보유 우선으로 유니버스 전체의 일봉을 백필·증분 수집 | 오늘 기술·스크리닝 근거가 부족해질 수 있다 |
| 3 | `benchmark_spy` | 1일 | 같은 일봉 경로로 SPY 벤치마크 저장 | `/me`의 SPY 대비 수익률만 `—`가 될 수 있다 |
| 4 | `disclosures` | 1일 | SEC 일일 인덱스 공시와 hard-event 근거 저장 | 공시 근거가 비지만 실패가 매도 신호로 둔갑하지 않는다 |
| 5 | `news` | 1일 | Alpaca 종목 뉴스를 수집·정규화 | 오늘 뉴스 근거가 줄고 다른 잡은 계속 돈다 |
| 6 | `news_wire` | 1일 | 무키 RSS 보도자료를 별도 실패 경계로 수집 | Alpaca 뉴스와 독립적으로 실패·성공한다 |
| 7 | `macro` | 1일 | FRED 계열 금리와 거시 국면 저장 | 최신 가용 거시 근거만 남는다 |
| 8 | `screening` | 1일 | 저장된 일봉·유니버스로 오늘의 픽 선정 | 이후 분석 대상이 생기지 않는다 |
| 9 | `insider_scoring` | 1일 | 픽의 Form 4 재량 거래를 채점해 투표·기권 기록 | 인사이더 표만 빠지고 분석은 독립 진행한다 |
| 10 | `analysis:aggressive` | 1일 | 공격형 STRATEGY 제안·critic·LLM usage 저장 | 공격형 후보만 격리 실패한다 |
| 11 | `analysis:conservative` | 1일 | 보수형 제안·critic·usage를 독립 저장 | 보수형 후보만 격리 실패한다 |
| 12 | `exits` | 1일 | 명제 붕괴·약세 판단·기간 청산. 장중 손절·익절은 WatchRunner 소유 | 일일 soft/time exit만 지연된다 |
| 13 | `allocation` | 1일 | 청산 뒤 확보된 현금·자리로 승인 후보를 사이징해 MockBroker 브래킷 매수 | 신규 매수가 생기지 않는다 |
| 14 | `daily_summary` | 1일·알림 설정 시 | 앞선 잡 성공·실패와 신규 매수를 텔레그램으로 한 번 요약 | 안내만 빠지고 앞선 원장은 유지된다 |

등록은 조건부다. 시장 데이터 공급자가 없으면 유니버스·일봉·SPY·Alpaca
뉴스가, 분석기가 없으면 persona 2종이, 텔레그램 설정이 없으면 summary가
빠질 수 있다. 운영 8020은 필요한 공급자와 알림이 있어 14종이 모두 등록된다.

이 14종과 장중 WatchRunner는 별개다. WatchRunner는 정규장 중 1분마다 보유+
당일 픽 현재가를 보고 브래킷 방어를 실행한다. rejudge가 켜지면 ±5% 사건과
뉴욕 10:00/12:45/15:15 스윕에서만 LLM을 호출한다.

### 4-7. 활성화 전 스냅샷·마이그레이션·롤백

아래 명령은 **app-v2-db-1이 127.0.0.1:5445에 healthy로 떠 있는 것을 먼저
확인한 뒤** 실행한다. `.env`의 5444 URL은 1차 DB이므로 사용하지 않는다.

```bash
cd ~/Documents/ClaudeCode/quantinue-v2/app-v2
db_identity="$(docker inspect -f '{{.Name}}|{{.State.Status}}|{{.State.Health.Status}}|{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostIp}}|{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostPort}}' app-v2-db-1)"
test "$db_identity" = '/app-v2-db-1|running|healthy|127.0.0.1|5445' || {
  echo '중단: app-v2-db-1이 정확한 127.0.0.1:5445 healthy DB가 아니다.' >&2
  exit 1
}
db_name_user="$(docker inspect app-v2-db-1 --format '{{range .Config.Env}}{{println .}}{{end}}' |
  awk -F= '$1=="POSTGRES_DB"{db=$2} $1=="POSTGRES_USER"{user=$2} END{print db ":" user}')"
test "$db_name_user" = 'quantinue:quantinue' || {
  echo '중단: app-v2 DB 이름/사용자가 정본과 다르다.' >&2
  exit 1
}
mkdir -p .runtime/preactivation-backups
stamp="$(date +%Y%m%dT%H%M%S%z)"
backup=".runtime/preactivation-backups/quantinue-5445-preactivation-${stamp}.dump"
(set -o noclobber; docker exec app-v2-db-1 pg_dump -Fc -U quantinue -d quantinue > "$backup")
test -s "$backup"
docker run --rm \
  -v "$PWD/$(dirname "$backup"):/backup:ro" postgres:17-alpine \
  pg_restore -l "/backup/$(basename "$backup")" >/dev/null

docker exec -i app-v2-db-1 psql -X -U quantinue -d quantinue \
  -v ON_ERROR_STOP=1 < db/migrations/mvp2.sql
# 같은 파일을 한 번 더 적용해 멱등성을 확인한다.
docker exec -i app-v2-db-1 psql -X -U quantinue -d quantinue \
  -v ON_ERROR_STOP=1 < db/migrations/mvp2.sql
```

실제 활성화·롤백 직전에는 아래 함수를 **같은 셸에서 먼저** 실행한다. 등록 잡
14개의 마지막 성공과 주기(유니버스 7일, 나머지 1일)를 현재 뉴욕 슬롯과
대조한다. 현재 슬롯의 daily 잡이 `running`/`failed`, 실행 기한이 온 잡이 미완료,
또는 스윕이 `running`이면 합계가 1 이상이므로 함수가 nonzero로 끝난다. 이
함수가 성공하기 전에는 YAML 수정·프로세스 종료·재기동을 하지 않는다.

```bash
preactivation_preflight() {
  db_identity="$(docker inspect -f '{{.Name}}|{{.State.Status}}|{{.State.Health.Status}}|{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostIp}}|{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostPort}}' app-v2-db-1)" || return 1
  test "$db_identity" = '/app-v2-db-1|running|healthy|127.0.0.1|5445' || return 1
  slot="$(TZ=America/New_York date +%F)"
  unsafe="$(docker exec -i app-v2-db-1 psql -X -U quantinue -d quantinue \
    -v ON_ERROR_STOP=1 -v slot="$slot" -At <<'SQL'
WITH registered(job_name, interval_days) AS (
  VALUES ('universe',7), ('daily_bars',1), ('benchmark_spy',1),
    ('disclosures',1), ('news',1), ('news_wire',1), ('macro',1),
    ('screening',1), ('insider_scoring',1), ('analysis:aggressive',1),
    ('analysis:conservative',1), ('exits',1), ('allocation',1),
    ('daily_summary',1)
), last_success AS (
  SELECT r.job_name, r.interval_days, max(j.slot_date) FILTER (WHERE j.status='succeeded') AS last_ok
  FROM registered r LEFT JOIN tb_job_run j USING (job_name)
  GROUP BY r.job_name, r.interval_days
), due AS (
  SELECT job_name FROM last_success
  WHERE last_ok IS NULL OR (DATE :'slot' - last_ok) >= interval_days
), unsafe_daily AS (
  SELECT job_name FROM tb_job_run
  WHERE slot_date=DATE :'slot' AND status IN ('running','failed')
  UNION
  SELECT d.job_name FROM due d
  WHERE NOT EXISTS (
    SELECT 1 FROM tb_job_run j
    WHERE j.job_name=d.job_name AND j.slot_date=DATE :'slot' AND j.status='succeeded'
  )
), unsafe_sweep AS (
  SELECT 'watch_sweep' AS job_name FROM tb_watch_sweep WHERE status='running'
)
SELECT (SELECT count(*) FROM unsafe_daily) + (SELECT count(*) FROM unsafe_sweep);
SQL
  )" || return 1
  test "$unsafe" = 0 || {
    echo "중단: running/failed/due 상태 ${unsafe}건 — YAML과 프로세스를 건드리지 않는다." >&2
    return 1
  }
}

preactivation_preflight
```

활성화 롤백은 마지막으로 켠 단계만 역순으로 끈다. 아래 각 블록은 위 함수를
정의한 같은 셸에서 그대로 복사해 실행한다. preflight가 실패하면 `&&` 뒤의
YAML 수정은 실행되지 않는다. Perl은 치환 대상이 없어도 0으로 끝나므로, 각
수정 직후 YAML을 구조적으로 다시 읽어 선택한 값이 정확히 `false`인지 확인한다.
치환 실패·잘못된 중첩·깨진 YAML이면 체인이 nonzero로 멈추고 재기동하지 않는다.

```bash
assert_watch_flag_false() {
  uv run python - "$1" <<'PY'
import sys
from pathlib import Path

import yaml

stage = sys.argv[1]
watch = yaml.safe_load(Path("config/pipeline.yaml").read_text())["mvp2"]["watch"]
value = watch["enabled"] if stage == "watch" else watch[stage]["enabled"]
if value is not False:
    raise SystemExit(f"중단: {stage}.enabled가 false가 아니다")
PY
}

# 스트림 단계 롤백
preactivation_preflight && perl -0pi -e \
  's/(    stream:\n      enabled:) true/$1 false/' config/pipeline.yaml && \
  assert_watch_flag_false stream

# 유료 장중 재판단 단계 롤백
preactivation_preflight && perl -0pi -e \
  's/(    rejudge:\n      enabled:) true/$1 false/' config/pipeline.yaml && \
  assert_watch_flag_false rejudge

# 1분 감시 단계 롤백
preactivation_preflight && perl -0pi -e \
  's/(  watch:\n    enabled:) true/$1 false/' config/pipeline.yaml && \
  assert_watch_flag_false watch

# 선택한 단계가 false인지 확인한 뒤 owner를 한 번만 정상 재기동한다.
preactivation_preflight || exit 1
lock_dir=.runtime/observation-owner.lock
test -s "$lock_dir/pid" && test -s "$lock_dir/start_identity" || {
  echo '중단: owner lock의 PID/start identity가 비었거나 없다.' >&2
  exit 1
}
owner_pid="$(cat "$lock_dir/pid")"
case "$owner_pid" in (*[!0-9]*|'') echo '중단: owner PID가 숫자가 아니다.' >&2; exit 1;; esac
kill -0 "$owner_pid" 2>/dev/null || {
  echo '중단: owner lock의 PID가 살아 있지 않다.' >&2
  exit 1
}
recorded_start="$(cat "$lock_dir/start_identity")"
actual_start="$(ps -o lstart= -p "$owner_pid" | xargs)"
test "$recorded_start" = "$actual_start" || {
  echo '중단: PID가 재사용됐거나 start identity가 다르다.' >&2
  exit 1
}
owner_command="$(ps -o command= -p "$owner_pid")"
case "$owner_command" in (*scripts/run_observation.sh*) :;;
  (*) echo '중단: lock PID가 observation launcher가 아니다.' >&2; exit 1;;
esac
owner_cwd="$(lsof -a -p "$owner_pid" -d cwd -Fn | sed -n 's/^n//p')"
test "$owner_cwd" = "$PWD" || {
  echo '중단: lock PID의 작업 디렉터리가 app-v2가 아니다.' >&2
  exit 1
}
kill -TERM "$owner_pid"
for _ in $(seq 1 30); do
  kill -0 "$owner_pid" 2>/dev/null || break
  sleep 1
done
! kill -0 "$owner_pid" 2>/dev/null || {
  echo '중단: 기존 owner가 30초 안에 종료되지 않았다.' >&2
  exit 1
}
nohup ./scripts/run_observation.sh >/dev/null 2>&1 &
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8020/health && break
  sleep 1
done
curl -fsS http://127.0.0.1:8020/health
```

이 설정 롤백은 이미 완료된 모의 주문·체결·시그널·LLM 비용 원장이나 이미
전송된 텔레그램 메시지를 되돌리지 않는다.

DB 자체를 스냅샷으로 복원하는 것은 마지막 수단이며 앱을 완전히 멈춘 별도
복구 작업이다. 원본을 덮어쓰기 전에 현재 DB를 다시 백업하고, 검증된 dump를
새 빈 DB에 `pg_restore --clean --if-exists`로 복원해 확인한 뒤 전환한다.

---

## 5. 코드를 고칠 때

⚠️ **관측 인스턴스는 그대로 두고 다른 포트로 띄운다.** 코드 작업용은
`--reload`가 필요한데, 리로드는 프로세스를 다시 띄우고 그게 잡 도중이면
슬롯이 굳는다(4-1).

```bash
cd ~/Documents/ClaudeCode/quantinue-v2/app-v2
QUANTINUE_DATA_MODE=public QUANTINUE_DATABASE_MODE=postgres \
QUANTINUE_DATABASE_URL="postgresql+asyncpg://quantinue:quantinue@127.0.0.1:5445/quantinue" \
QUANTINUE_LLM_MODE=mock QUANTINUE_BACKGROUND_WORKERS=0 QUANTINUE_OPS_ALERTS=0 \
uv run uvicorn quantinue.main:app --port 8021 --reload \
  --reload-dir src/quantinue --reload-include '*.css' --reload-include '*.html'
```

8021 명령의 세 스위치는 생략하지 않는다. 포트 번호는 실행 역할을 결정하지
않으며, `BACKGROUND_WORKERS=0`인 프로세스는 YAML의 jobs/watch 값이 켜져 있어도
자동 잡·장중 감시·운영 알림을 만들거나 시작하지 않는다.

⚠️ **`--reload`가 없으면 CSS를 고쳐도 화면이 안 바뀐다** — `dashboard.css`는
import 시점에 한 번만 읽어 HTML에 인라인된다.

### 검증

```bash
cd app-v2
uv run pytest tests/unit tests/test_pipeline_dashboard.py tests/test_my_account.py -q
uv run ruff check src tests scripts      # 파이프(| tail) 걸지 말 것 — 종료코드가 가려진다
./scripts/scan_secrets.sh                # 커밋 전
```

통합 테스트는 **일회용 DB**가 필요하다(같은 컨테이너에서 두 번 못 돌린다 —
멱등 가드가 옛 행을 지켜내 실패를 가린다):

```bash
docker rm -f qn-itest 2>/dev/null
docker run -d --name qn-itest -e POSTGRES_USER=quantinue -e POSTGRES_PASSWORD=quantinue \
  -e POSTGRES_DB=quantinue -p 127.0.0.1:5490:5432 postgres:16
# ⚠️ 준비될 때까지 기다린다. 바로 스키마를 부으면 일부만 들어가고
# 테스트가 error 몇 건으로 끝난다 — 실제로 그렇게 6건이 났다.
until docker exec qn-itest pg_isready -U quantinue -q; do sleep 1; done
docker exec -i qn-itest psql -q -U quantinue -d quantinue < db/schema.sql
QUANTINUE_TEST_DATABASE_URL="postgresql+asyncpg://quantinue:quantinue@127.0.0.1:5490/quantinue" \
  uv run pytest tests/integration -q -p no:unraisableexception
docker rm -f qn-itest
```

⚠️ 포트가 5480 → **5490**이다. 5480은 다른 작업자의 컨테이너가 점유하고
있을 수 있다(2026-07-21 실제로 그랬다).

---

## 6. 알아두면 좋은 것

- **자원**: 앱 24MB · DB 201MB · 유휴 CPU 0%. 로컬 LLM 시절엔 부담이
  GPU 하루 15분이었고, openai 전환 후엔 **비용**(일 예산 상한 $3,
  실사용 ~$0.05/일 예상)으로 바뀌었다.
- **체결은 진짜 돈이 아니다.** 로컬 시뮬(MockBroker)이고 시세만 실물(Alpaca)이다.
  실제 주문이 브로커로 나가는 것은 아직 안 한다.
- **`.env`를 `.env.example`로 덮어쓰지 않는다.** 키가 다 날아간다.
- **`app/`(1차)은 다른 작업자 것이다.** 건드리지 않는다.
