#!/usr/bin/env bash
# S5 소재: 촬영 직후 무결 검증을 실제로 돌려 그 출력을 그대로 남긴다.
# 여기서 만드는 건 "화면용 그림"이 아니라 실행 기록이다 — 렌더링하는 쪽은
# 이 파일의 내용을 한 글자도 고치지 않는다.
set -uo pipefail
cd "$(dirname "$0")/../../app-v2"

run() {  # 명령을 화면에 적고, 그 출력을 그대로 잇는다
  printf '$ %s\n' "$1"
  eval "$1" 2>&1
  printf '\n'
}

echo "# 데모 원장 무결 검증 — $(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '\n'

run './scripts/demo_preflight.sh'

# LLM 호출수·비용은 일부러 빼둔다. 이 데모는 운영 원장을 통째로 복사해
# 이어받기 때문에 그 컬럼에는 **운영에서 실제로 쓴 값**이 섞여 있다.
# "모의 AI"라고 적힌 화면에 달러 금액이 뜨면 그 한 줄이 영상 전체를
# 의심하게 만든다. 무사건 tick의 LLM 0콜은 preflight가 이미 검사한다.
run "docker exec qn-demo-db psql -X -U quantinue -d quantinue -c \"
SELECT (SELECT count(*) FROM tb_order) AS 주문,
       (SELECT count(*) FROM tb_fill)  AS 체결,
       (SELECT count(*) FROM (SELECT idempotency_key FROM tb_order
                              GROUP BY 1 HAVING count(*)>1) d) AS 중복주문키,
       (SELECT count(*) FROM (SELECT broker_fill_id FROM tb_fill
                              GROUP BY 1 HAVING count(*)>1) d) AS 중복체결ID;\""

# 체결시각도 뺀다 — 각본 매도는 실제 벽시계로, 매수는 고정 시계(14:00 UTC)로
# 찍혀서 나란히 놓으면 "매도가 매수보다 먼저"로 읽힌다. 데모 하네스의 시계
# 아티팩트이지 원장의 문제가 아니다.
run "docker exec qn-demo-db psql -X -U quantinue -d quantinue -c \"
SELECT o.ticker, f.side AS 방향, f.quantity AS 수량, f.price AS 체결가
FROM tb_fill f JOIN tb_order o ON o.id = f.order_id
WHERE o.ticker IN ('VRDN','NVEX','HLXM') ORDER BY o.ticker, f.side;\""
