#!/bin/sh
set -eu

[ "${ALLOW_RECOVERY_DRILL:-no}" = "yes" ] || { echo "必须设置 ALLOW_RECOVERY_DRILL=yes" >&2; exit 1; }
: "${TASK_ID:?必须设置待验证的非终态 TASK_ID}"
case "$TASK_ID" in
  *[!A-Za-z0-9_-]*|'') echo "TASK_ID 格式无效" >&2; exit 1 ;;
esac

compose() {
  docker compose --env-file .env -f infra/compose.yaml "$@"
}

baseline="/tmp/inkforge-recovery-${TASK_ID}.json"
compose exec -T core-api python -m inkforge_core.ops.recovery_audit snapshot \
  --task-id "$TASK_ID" --output "$baseline"
job_id="$(compose exec -T core-api python -m inkforge_core.ops.recovery_audit job-id \
  --task-id "$TASK_ID" | tr -d '\r')"
[ -n "$job_id" ] || { echo "无法计算当前队列任务标识" >&2; exit 1; }

compose stop agent-service
compose exec -T redis redis-cli ZREM inkforge:runs:ready "$job_id" >/dev/null
compose exec -T redis redis-cli ZREM inkforge:runs:processing "$job_id" >/dev/null
compose exec -T redis redis-cli HDEL inkforge:runs:payloads "$job_id" >/dev/null
compose exec -T redis redis-cli HDEL inkforge:runs:statuses "$job_id" >/dev/null
compose exec -T redis redis-cli HDEL inkforge:runs:leases "$job_id" >/dev/null
compose exec -T redis redis-cli HDEL inkforge:runs:attempts "$job_id" >/dev/null
compose exec -T redis redis-cli HDEL inkforge:runs:scores "$job_id" >/dev/null
compose start agent-service
i=0
until compose exec -T agent-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=5)"; do
  i=$((i + 1))
  [ "$i" -lt 30 ] || { echo "Agent Service 重启后未就绪" >&2; exit 1; }
  sleep 2
done

i=0
while [ "$i" -lt 60 ]; do
  if compose exec -T core-api python -m inkforge_core.ops.recovery_audit verify \
    --task-id "$TASK_ID" --output "$baseline"; then
    echo "Agent Service 重启接管验证通过：$TASK_ID"
    exit 0
  else
    status=$?
  fi
  [ "$status" -eq 2 ] || exit "$status"
  i=$((i + 1))
  sleep 2
done

echo "等待任务恢复完成超时" >&2
exit 1
