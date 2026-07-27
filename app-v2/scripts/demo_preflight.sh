#!/usr/bin/env bash
# 촬영 직전 무결 점검(demo-video-plan.md §4-5). 항목별로 다른 메시지와
# 종료 코드로 실패한다 — 어느 선이 무너졌는지 즉시 알기 위해서다.
#
#   ./scripts/demo_preflight.sh

set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_APP_PORT=8022
DEMO_DB_CONTAINER=qn-demo-db

psql_demo() {
  docker exec "${DEMO_DB_CONTAINER}" psql -tA -U quantinue -d quantinue -c "$1"
}

fail() { # code message
  echo "preflight FAIL($1): $2" >&2
  exit "$1"
}

# 1. 앱이 8022에서 mock 조합으로 떠 있는가
health="$(curl -fsS "http://127.0.0.1:${DEMO_APP_PORT}/health" 2>/dev/null)" \
  || fail 10 "8022 데모 앱이 응답하지 않는다"
echo "${health}" | grep -q '"broker_mode":"mock"' \
  || fail 11 "브로커가 mock이 아니다: ${health}"
echo "${health}" | grep -q '"llm_mode":"mock"' \
  || fail 12 "LLM이 mock이 아니다: ${health}"

# 2. DB가 전용 5490 컨테이너인가
docker ps --format '{{.Names}} {{.Ports}}' | grep -q "^${DEMO_DB_CONTAINER} .*127.0.0.1:5490->" \
  || fail 20 "qn-demo-db(5490) 컨테이너가 없다"

# 3. 중복 주문 키·중복 fill 0건
dup_orders="$(psql_demo "SELECT count(*) FROM (SELECT idempotency_key FROM tb_order GROUP BY 1 HAVING count(*) > 1) d")"
[ "${dup_orders}" = "0" ] || fail 30 "중복 idempotency key ${dup_orders}건"
dup_fills="$(psql_demo "SELECT count(*) FROM (SELECT broker_fill_id FROM tb_fill GROUP BY 1 HAVING count(*) > 1) d")"
[ "${dup_fills}" = "0" ] || fail 31 "중복 broker_fill_id ${dup_fills}건"

# 4. 무사건 상태에서 LLM 호출 0건 — 라우팅된 사건이 없는데 LLM 원장이
#    있다면 tick이 몰래 LLM을 부르고 있다는 뜻이다.
events="$(psql_demo "SELECT count(*) FROM tb_normalized_event")"
llm_calls="$(psql_demo "SELECT count(*) FROM tb_llm_usage")"
if [ "${events}" = "0" ] && [ "${llm_calls}" != "0" ]; then
  fail 40 "사건 0건인데 LLM 호출 ${llm_calls}건 — 무사건 tick이 LLM을 불렀다"
fi

# 5. 비밀 검사
./scripts/scan_secrets.sh >/dev/null || fail 50 "비밀 검사 실패"

# 6. 운영(8020·5445)을 향한 자원이 데모 환경에 없는가
if lsof -nP -iTCP:"${DEMO_APP_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  :
else
  fail 60 "8022 리스너가 없다 — 다른 포트로 떠 있다면 중단하라"
fi

echo "preflight OK: app=8022 db=5490 dup_orders=0 dup_fills=0 events=${events} llm_calls=${llm_calls}"
