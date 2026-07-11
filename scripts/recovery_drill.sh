#!/bin/sh
set -eu

[ "${ALLOW_RECOVERY_DRILL:-no}" = "yes" ] || { echo "必须设置 ALLOW_RECOVERY_DRILL=yes" >&2; exit 1; }
: "${TASK_ID:?必须设置待验证的非终态 TASK_ID}"

compose="docker compose --env-file .env -f infra/compose.yaml"
$compose stop agent-service
$compose start agent-service
i=0
until $compose exec -T agent-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=5)"; do
  i=$((i + 1))
  [ "$i" -lt 30 ] || { echo "Agent Service 重启后未就绪" >&2; exit 1; }
  sleep 2
done

echo "Agent Service 已重启。请在 Core 调试接口确认任务 ${TASK_ID} 从最后稳定检查点继续，且未重复生成草案或扣费。"
