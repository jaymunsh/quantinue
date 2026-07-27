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
    "$@"
}

require_free_demo_port() {
  if lsof -nP -iTCP:"${DEMO_APP_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "중단: ${DEMO_APP_PORT} 포트가 이미 사용 중이다." >&2
    exit 1
  fi
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
