#!/usr/bin/env bash
# 촬영용 일회용 데모 런타임: 포트 8022 + 전용 DB 5490.
#
#   ./scripts/run_demo.sh start    # DB 생성 → 스키마 → seed → 앱 기동
#   ./scripts/run_demo.sh reset    # DB를 버리고 같은 seed로 복원 (앱 재기동)
#   ./scripts/run_demo.sh stop     # 앱·DB·lock 제거
#   ./scripts/run_demo.sh status   # 현재 상태 표시
#
# 금지선(demo-video-plan.md §5): 운영 8020·8021, DB 5444·5445·5480을 절대
# 건드리지 않는다. 이 스크립트의 모든 자원 이름은 demo 전용이다.

set -euo pipefail

cd "$(dirname "$0")/.."

DEMO_APP_PORT=8022
DEMO_DB_PORT=5490
DEMO_DB_CONTAINER=qn-demo-db
DEMO_DB_URL="postgresql+asyncpg://quantinue:quantinue@127.0.0.1:${DEMO_DB_PORT}/quantinue"
RUNTIME_DIR=".runtime/demo"
PID_FILE="${RUNTIME_DIR}/app.pid"
LOG_FILE="${RUNTIME_DIR}/app.log"

# 데모가 실수로라도 다른 포트를 향하지 못하게 여기서 못 박는다. 5490이
# 아닌 값이 어떻게든 들어오면 파이썬 쪽 가드(_require_demo_settings)가
# 연결 전에 nonzero로 거부한다.
demo_env() {
  env \
    QUANTINUE_DATABASE_MODE=postgres \
    QUANTINUE_DATABASE_URL="${DEMO_DB_URL}" \
    QUANTINUE_LLM_MODE=mock \
    QUANTINUE_BROKER_MODE=mock \
    QUANTINUE_DATA_MODE=fixture \
    QUANTINUE_BACKGROUND_WORKERS=1 \
    QUANTINUE_OPS_ALERTS=0 \
    `# 세션 키를 고정하는 이유: 비우면 기동마다 무작위로 생겨 reset 때마다
     # 로그인이 풀린다. 촬영은 reset을 반복하는 작업이라 그때마다 재로그인이
     # 장면 시간을 잡아먹는다. 이 값은 일회용 데모 런타임 전용이고 운영
     # .env와 무관하다.` \
    QUANTINUE_SESSION_SECRET="demo-only-not-a-secret-0000000000" \
    "$@"
}

require_free_demo_port() {
  if lsof -nP -iTCP:"${DEMO_APP_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "중단: ${DEMO_APP_PORT} 포트가 이미 사용 중이다." >&2
    exit 1
  fi
}

drop_test_accounts() {
  # 회귀 검증을 하며 만든 계좌(TEST-*)는 운영 원장에 남아 있지만 시연의
  # 소재가 아니다 — 화면이 "계좌 11개"라고 세면 청중은 그게 다 운용 중인
  # 계좌인 줄 안다. **일회용 데모 DB에서만** 지운다. 운영 5445는 읽기
  # 전용이라 손대지 않으며, 그쪽 원장에는 이 계좌들이 회귀 증거로 남는다.
  #
  # 지우는 순서는 외래키 역순이다. 청산 주문이 원주문을 가리키므로
  # (closes_order_id) 주문은 두 번에 나눠 지운다.
  echo "검증용 계좌(TEST-*) 정리 중 — 데모 DB에서만…"
  docker exec -i "${DEMO_DB_CONTAINER}" psql -q -v ON_ERROR_STOP=1 \
    -U quantinue -d quantinue >/dev/null <<'SQL'
CREATE TEMP VIEW demo_test_accounts AS
  SELECT id FROM tb_account WHERE broker_account_id LIKE 'TEST-%';
DELETE FROM tb_fill WHERE order_id IN (
  SELECT id FROM tb_order WHERE account_id IN (SELECT id FROM demo_test_accounts));
DELETE FROM tb_order WHERE closes_order_id IN (
  SELECT id FROM tb_order WHERE account_id IN (SELECT id FROM demo_test_accounts));
DELETE FROM tb_order WHERE account_id IN (SELECT id FROM demo_test_accounts);
DELETE FROM tb_account_equity_daily WHERE account_id IN (SELECT id FROM demo_test_accounts);
DELETE FROM tb_account WHERE id IN (SELECT id FROM demo_test_accounts);
SQL
}

start_db() {
  docker rm -f "${DEMO_DB_CONTAINER}" >/dev/null 2>&1 || true
  docker run -d --name "${DEMO_DB_CONTAINER}" \
    -e POSTGRES_USER=quantinue -e POSTGRES_PASSWORD=quantinue \
    -e POSTGRES_DB=quantinue \
    -p "127.0.0.1:${DEMO_DB_PORT}:5432" postgres:16 >/dev/null
  # 준비 전에 스키마를 부으면 일부만 들어간다(운영 runbook §5 실측).
  until docker exec "${DEMO_DB_CONTAINER}" pg_isready -U quantinue -d quantinue -q; do
    sleep 1
  done
  if [[ "${DEMO_WITH_HISTORY:-0}" == "1" ]]; then
    # 운영 원장(5445)을 **읽기 전용 dump**로 복사해 이어받는다 — 몇 주치
    # 수집·판단·계좌 곡선이 그대로 데모의 출발 상태가 된다. 운영 쪽에는
    # pg_dump(SELECT)만 나가고 어떤 쓰기도 하지 않는다(금지선).
    echo "운영 원장 스냅샷 복사 중 (5445 → 5490, 읽기 전용 dump)…"
    docker exec app-v2-db-1 pg_dump -U quantinue -d quantinue \
      --no-owner --no-privileges \
      | docker exec -i "${DEMO_DB_CONTAINER}" psql -q -U quantinue -d quantinue \
      >/dev/null
    drop_test_accounts
  fi
  # 스키마는 멱등이라 빈 DB든 복사본 위든 부족한 조각만 채운다.
  docker exec -i "${DEMO_DB_CONTAINER}" psql -q -v ON_ERROR_STOP=1 \
    -U quantinue -d quantinue <db/schema.sql
}

seed_ledger() {
  demo_env uv run python -m quantinue.demo.seed_cli
}

start_app() {
  require_free_demo_port
  mkdir -p "${RUNTIME_DIR}"
  demo_env uv run uvicorn --factory quantinue.demo.app:create_demo_app \
    --host 127.0.0.1 --port "${DEMO_APP_PORT}" >"${LOG_FILE}" 2>&1 &
  echo $! >"${PID_FILE}"
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${DEMO_APP_PORT}/health" >/dev/null 2>&1; then
      echo "demo app ready: http://127.0.0.1:${DEMO_APP_PORT} (log: ${LOG_FILE})"
      return 0
    fi
    sleep 1
  done
  echo "중단: 데모 앱이 30초 안에 health를 열지 못했다. ${LOG_FILE}를 보라." >&2
  stop_app
  exit 1
}

stop_app() {
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" >/dev/null 2>&1 || true
    rm -f "${PID_FILE}"
  fi
  # uv run 래퍼를 죽여도 uvicorn 자식이 살아남을 수 있다(실측). 데모 전용
  # 포트의 리스너를 직접 정리한다 — 8022는 이 스크립트만 쓰는 포트다.
  local leftover
  leftover="$(lsof -tiTCP:"${DEMO_APP_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${leftover}" ]]; then
    kill ${leftover} >/dev/null 2>&1 || true
    sleep 1
  fi
}

case "${1:-}" in
  start)
    start_db
    seed_ledger
    start_app
    ;;
  reset)
    stop_app
    start_db
    seed_ledger
    start_app
    ;;
  stop)
    stop_app
    docker rm -f "${DEMO_DB_CONTAINER}" >/dev/null 2>&1 || true
    rm -rf "${RUNTIME_DIR}"
    echo "demo runtime removed."
    ;;
  status)
    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
      echo "app: running (pid $(cat "${PID_FILE}"), port ${DEMO_APP_PORT})"
    else
      echo "app: stopped"
    fi
    docker ps --filter "name=${DEMO_DB_CONTAINER}" --format 'db: {{.Names}} {{.Status}} {{.Ports}}'
    ;;
  *)
    echo "usage: $0 {start|reset|stop|status}" >&2
    exit 64
    ;;
esac
