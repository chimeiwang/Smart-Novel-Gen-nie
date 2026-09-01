#!/bin/sh
set -eu

: "${EXECUTION_REDIS_CONTAINER:?必须设置 execution Redis 容器名}"
: "${RESTORE_EPOCH:?必须设置恢复 epoch}"
: "${SNAPSHOT_SHA256:?必须设置恢复快照 SHA-256}"
: "${RECONCILIATION_REPORT_SHA256:?必须设置具名对账报告 SHA-256}"
: "${CLEAR_CONFIRM_TOKEN:?必须设置精确解除确认令牌}"

for digest in "$SNAPSHOT_SHA256" "$RECONCILIATION_REPORT_SHA256"; do
  case "$digest" in
    *[!0-9a-f]*|'') echo "SHA-256 格式无效" >&2; exit 1 ;;
  esac
  [ "${#digest}" -eq 64 ] || { echo "SHA-256 格式无效" >&2; exit 1; }
done
case "$EXECUTION_REDIS_CONTAINER" in
  *[!A-Za-z0-9_.-]*|'') echo "execution Redis 容器名无效" >&2; exit 1 ;;
esac
case "$RESTORE_EPOCH" in
  *[!A-Za-z0-9_.:-]*|'') echo "恢复 epoch 格式无效" >&2; exit 1 ;;
esac

expected_confirm="CLEAR_EXECUTION_JOURNAL_QUARANTINE:${RESTORE_EPOCH}:${SNAPSHOT_SHA256}:${RECONCILIATION_REPORT_SHA256}"
[ "$CLEAR_CONFIRM_TOKEN" = "$expected_confirm" ] || {
  echo "execution journal quarantine 解除令牌不匹配" >&2
  exit 1
}

quarantine_key="inkforge:executions:restore:quarantine"
audit_key="inkforge:executions:restore:last-reconciliation"
expected_marker="epoch=${RESTORE_EPOCH};snapshotSha256=${SNAPSHOT_SHA256}"
audit_value="epoch=${RESTORE_EPOCH};snapshotSha256=${SNAPSHOT_SHA256};reportSha256=${RECONCILIATION_REPORT_SHA256}"
pre_waitaof_output="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-cli --raw WAITAOF 1 0 5000
)"
pre_local_aof_ack="$(printf '%s\n' "$pre_waitaof_output" | sed -n '1p' | tr -d '\r')"
[ "$pre_local_aof_ack" = "1" ] || {
  echo "execution Redis 当前没有本地 AOF 确认，拒绝解除 quarantine" >&2
  exit 1
}
result="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" redis-cli --raw EVAL \
    "if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end redis.call('SET', KEYS[2], ARGV[2]) redis.call('DEL', KEYS[1]) return 1" \
    2 "$quarantine_key" "$audit_key" "$expected_marker" "$audit_value"
)"
[ "$result" = "1" ] || {
  echo "quarantine marker 与具名恢复事实不一致，拒绝解除" >&2
  exit 1
}
waitaof_output="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-cli --raw WAITAOF 1 0 5000
)"
local_aof_ack="$(printf '%s\n' "$waitaof_output" | sed -n '1p' | tr -d '\r')"
[ "$local_aof_ack" = "1" ] || {
  # 解除动作没有耐久确认时，立即恢复当前实例的 fail-closed marker。
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" redis-cli --raw SET \
    "$quarantine_key" "$expected_marker" >/dev/null || true
  echo "quarantine 解除未取得本地 AOF 确认，已恢复运行时隔离" >&2
  exit 1
}
echo "execution journal quarantine 已按具名对账报告解除"
