#!/bin/sh
set -eu
umask 077

: "${SNAPSHOT_PATH:?必须设置 execution journal RDB 快照路径}"
: "${SNAPSHOT_SHA256:?必须设置快照 SHA-256}"
: "${TARGET_VOLUME:?必须设置全新的恢复卷名称}"
: "${RESTORE_EPOCH:?必须设置恢复 epoch}"
: "${RESTORE_CONFIRM_TOKEN:?必须设置精确恢复确认令牌}"

case "$SNAPSHOT_SHA256" in
  *[!0-9a-f]*|'') echo "快照 SHA-256 格式无效" >&2; exit 1 ;;
esac
[ "${#SNAPSHOT_SHA256}" -eq 64 ] || { echo "快照 SHA-256 格式无效" >&2; exit 1; }
case "$RESTORE_EPOCH" in
  *[!A-Za-z0-9_.:-]*|'') echo "恢复 epoch 格式无效" >&2; exit 1 ;;
esac
case "$TARGET_VOLUME" in
  inkforge_execution_redis_restore_[A-Za-z0-9_.-]*) ;;
  *) echo "恢复只能写入具名的新隔离卷" >&2; exit 1 ;;
esac

expected_confirm="RESTORE_EXECUTION_JOURNAL:${TARGET_VOLUME}:${RESTORE_EPOCH}:${SNAPSHOT_SHA256}"
[ "$RESTORE_CONFIRM_TOKEN" = "$expected_confirm" ] || {
  echo "execution journal 恢复确认令牌不匹配" >&2
  exit 1
}
[ -f "$SNAPSHOT_PATH" ] && [ -r "$SNAPSHOT_PATH" ] || {
  echo "execution journal 快照不存在或不可读" >&2
  exit 1
}
printf '%s  %s\n' "$SNAPSHOT_SHA256" "$SNAPSHOT_PATH" | sha256sum -c - >/dev/null

command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
docker image inspect redis:7.4-alpine >/dev/null 2>&1 || {
  echo "缺少固定 Redis 运行镜像" >&2
  exit 1
}

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
config_path="${script_dir%/}/../infra/redis/execution-redis.conf"
[ -r "$config_path" ] || { echo "缺少 execution Redis 配置" >&2; exit 1; }
snapshot_dir="$(CDPATH= cd -- "$(dirname -- "$SNAPSHOT_PATH")" && pwd)"
snapshot_name="$(basename -- "$SNAPSHOT_PATH")"
snapshot_absolute="${snapshot_dir%/}/${snapshot_name}"

docker run --rm --network none --read-only --cap-drop ALL \
  --mount "type=bind,source=$snapshot_absolute,target=/restore/snapshot.rdb,readonly" \
  --entrypoint redis-check-rdb redis:7.4-alpine \
  /restore/snapshot.rdb >/dev/null

docker volume create "$TARGET_VOLUME" >/dev/null
docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN \
  --user 0:0 \
  --mount "type=volume,source=$TARGET_VOLUME,target=/data" \
  --entrypoint /bin/chown redis:7.4-alpine 999:999 /data
docker run --rm --network none --read-only --cap-drop ALL --user 999:999 \
  --mount "type=volume,source=$TARGET_VOLUME,target=/data" \
  --entrypoint /bin/sh redis:7.4-alpine \
  -c 'test -z "$(find /data -mindepth 1 -maxdepth 1 -print -quit)"' || {
    echo "恢复目标卷不是空卷，拒绝覆盖" >&2
    exit 1
  }
docker run --rm --network none --read-only --cap-drop ALL --user 999:999 \
  --mount "type=volume,source=$TARGET_VOLUME,target=/data" \
  --mount "type=bind,source=$snapshot_absolute,target=/restore/snapshot.rdb,readonly" \
  --entrypoint /bin/cp redis:7.4-alpine /restore/snapshot.rdb /data/dump.rdb

restore_container="inkforge-execution-restore-${RESTORE_EPOCH}"
case "$restore_container" in
  *[!A-Za-z0-9_.-]*) echo "恢复容器名无效" >&2; exit 1 ;;
esac
cleanup_restore_container() {
  docker rm -f "$restore_container" >/dev/null 2>&1 || true
}
trap cleanup_restore_container EXIT HUP INT TERM
docker run --detach --name "$restore_container" --network none --read-only \
  --security-opt no-new-privileges:true --cap-drop ALL --user 999:999 \
  --mount "type=volume,source=$TARGET_VOLUME,target=/data" \
  --mount "type=bind,source=$config_path,target=/usr/local/etc/redis/execution-redis.conf,readonly" \
  --tmpfs /tmp:size=8m,mode=1777 \
  redis:7.4-alpine redis-server /usr/local/etc/redis/execution-redis.conf >/dev/null

attempt=0
until docker exec --user 999:999 "$restore_container" redis-cli PING >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 30 ] || { echo "恢复 Redis 未能启动" >&2; exit 1; }
  sleep 1
done
marker="epoch=${RESTORE_EPOCH};snapshotSha256=${SNAPSHOT_SHA256}"
docker exec --user 999:999 "$restore_container" redis-cli --raw SET \
  inkforge:executions:restore:quarantine "$marker" | grep -q '^OK$'
waitaof_output="$(
  docker exec --user 999:999 "$restore_container" \
    redis-cli --raw WAITAOF 1 0 5000
)"
local_aof_ack="$(printf '%s\n' "$waitaof_output" | sed -n '1p' | tr -d '\r')"
[ "$local_aof_ack" = "1" ] || {
  echo "恢复 quarantine marker 未取得本地 AOF 确认" >&2
  exit 1
}
docker exec --user 999:999 "$restore_container" redis-cli --raw INFO persistence \
  | grep -q '^aof_last_write_status:ok'
cleanup_restore_container
trap - EXIT HUP INT TERM

echo "execution journal 已恢复到隔离卷并保持 quarantine：$TARGET_VOLUME"
echo "在具名 Core/供应商对账完成前不得把该卷接入可调用模型的 Agent"
