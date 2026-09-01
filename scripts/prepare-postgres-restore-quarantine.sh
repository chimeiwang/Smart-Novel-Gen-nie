#!/bin/sh
set -eu
umask 077

: "${POSTGRES_BACKUP_DIR:?必须设置已验证的 PostgreSQL 备份目录}"
: "${EXECUTION_REDIS_CONTAINER:?必须设置当前 execution Redis 容器身份}"
: "${RESTORE_EPOCH:?必须设置 PostgreSQL 恢复 epoch}"
: "${POSTGRES_RESTORE_CONFIRM_FILE:?必须设置 0600 精确确认令牌文件}"
: "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:?必须显式确认 V2 route mode}"
: "${EXECUTION_DISPATCH_STOPPED:?必须显式确认 execution dispatch 已停止}"
: "${CORE_API_CONTAINER:?必须设置已停止的 Core 容器身份}"
: "${AGENT_SERVICE_CONTAINER:?必须设置已停止的 Agent 容器身份}"

[ "$DURABLE_AGENT_EXECUTION_ROUTE_MODE" = "off" ] || {
  echo "PostgreSQL restore 前必须先完成 V2 route-off" >&2
  exit 1
}
[ "$EXECUTION_DISPATCH_STOPPED" = "true" ] || {
  echo "PostgreSQL restore 前必须停止新的 execution dispatch" >&2
  exit 1
}

case "$EXECUTION_REDIS_CONTAINER" in
  *[!A-Za-z0-9_.-]*|'') echo "execution Redis 容器身份无效" >&2; exit 1 ;;
esac
case "$CORE_API_CONTAINER" in
  *[!A-Za-z0-9_.-]*|'') echo "Core 容器身份无效" >&2; exit 1 ;;
esac
case "$AGENT_SERVICE_CONTAINER" in
  *[!A-Za-z0-9_.-]*|'') echo "Agent 容器身份无效" >&2; exit 1 ;;
esac
case "$RESTORE_EPOCH" in
  postgres-restore-[A-Za-z0-9_.:-]*) ;;
  *) echo "PostgreSQL 恢复 epoch 必须使用 postgres-restore- 前缀" >&2; exit 1 ;;
esac

for command_name in docker python3 sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "PostgreSQL 恢复隔离准备缺少必要命令：$command_name" >&2
    exit 1
  }
done
[ -d "$POSTGRES_BACKUP_DIR" ] && [ ! -L "$POSTGRES_BACKUP_DIR" ] || {
  echo "PostgreSQL 备份目录不存在或是符号链接" >&2
  exit 1
}
for required_file in database.dump SHA256SUMS recovery-boundary.meta; do
  [ -s "$POSTGRES_BACKUP_DIR/$required_file" ] \
    && [ ! -L "$POSTGRES_BACKUP_DIR/$required_file" ] || {
    echo "PostgreSQL 备份缺少恢复边界文件" >&2
    exit 1
  }
done
python3 - "$POSTGRES_BACKUP_DIR/SHA256SUMS" <<'PY'
import re
import sys
from pathlib import Path

allowed = {
    "database.dump",
    "recovery-boundary.meta",
    "uploads.tar.gz",
    "execution-journal.rdb",
    "execution-journal.meta",
    "durable-agent-migration.meta",
}
names: list[str] = []
try:
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None:
            raise ValueError
        names.append(match.group(2))
except (OSError, UnicodeError, ValueError):
    print("postgres-backup-checksums:invalid", file=sys.stderr)
    raise SystemExit(1) from None
if (
    len(names) != len(set(names))
    or not {"database.dump", "recovery-boundary.meta"}.issubset(names)
    or not set(names) <= allowed
):
    print("postgres-backup-checksums:unexpected-files", file=sys.stderr)
    raise SystemExit(1)
PY
(
  cd -- "$POSTGRES_BACKUP_DIR"
  sha256sum --check SHA256SUMS >/dev/null
) || { echo "PostgreSQL 备份校验和失败" >&2; exit 1; }
grep -qx 'postgresRestoreRequiresExecutionQuarantine=true' \
  "$POSTGRES_BACKUP_DIR/recovery-boundary.meta" || {
    echo "备份未声明 PostgreSQL restore 前 execution quarantine" >&2
    exit 1
  }

database_sha256="$(sha256sum "$POSTGRES_BACKUP_DIR/database.dump" | cut -d ' ' -f 1)"
case "$database_sha256" in
  *[!0-9a-f]*|'') echo "PostgreSQL 备份 SHA-256 格式无效" >&2; exit 1 ;;
esac
[ "${#database_sha256}" -eq 64 ] || {
  echo "PostgreSQL 备份 SHA-256 格式无效" >&2
  exit 1
}

# 令牌文件只用于证明人工准备动作，内容不进入 argv、stdout 或容器环境。
python3 - "$POSTGRES_RESTORE_CONFIRM_FILE" "$RESTORE_EPOCH" "$database_sha256" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = f"PREPARE_POSTGRES_RESTORE_QUARANTINE:{sys.argv[2]}:{sys.argv[3]}"
try:
    metadata = path.stat()
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError
    value = path.read_text(encoding="utf-8")
except (OSError, UnicodeError, ValueError):
    print("postgres-restore-confirmation-file:invalid", file=sys.stderr)
    raise SystemExit(1) from None
if value.endswith("\n"):
    value = value[:-1]
if "\n" in value or "\r" in value or value != expected:
    print("postgres-restore-confirmation-token:mismatch", file=sys.stderr)
    raise SystemExit(1)
PY

inspect_compose_container_facts() {
  docker inspect --format \
    '{{ index .Config.Labels "com.docker.compose.project" }}|{{ index .Config.Labels "com.docker.compose.project.config_files" }}|{{ index .Config.Labels "com.docker.compose.project.working_dir" }}|{{ index .Config.Labels "com.docker.compose.service" }}|{{.State.Status}}|{{.State.Running}}|{{.State.Paused}}|{{.State.Restarting}}' \
    "$1"
}

parse_compose_container_facts() {
  facts_value="$1"
  previous_ifs="$IFS"
  IFS='|'
  read -r fact_project fact_config_files fact_working_dir fact_service \
    fact_status fact_running fact_paused fact_restarting <<EOF
$facts_value
EOF
  IFS="$previous_ifs"
}

resolve_authoritative_compose_identity() {
  if redis_facts="$(inspect_compose_container_facts "$EXECUTION_REDIS_CONTAINER")"; then
    :
  else
    echo "无法读取 execution Redis 的 Compose 身份" >&2
    exit 1
  fi
  parse_compose_container_facts "$redis_facts"
  authoritative_project="$fact_project"
  authoritative_config_files="$fact_config_files"
  authoritative_working_dir="$fact_working_dir"
  case "$authoritative_project" in
    ""|"<no value>"|*[!A-Za-z0-9_.-]*)
      echo "execution Redis Compose project 身份无效" >&2
      exit 1
      ;;
  esac
  for identity_value in "$authoritative_config_files" "$authoritative_working_dir"; do
    case "$identity_value" in
      ""|"<no value>"|*'|'*)
        echo "execution Redis Compose config 身份无效" >&2
        exit 1
        ;;
    esac
  done
  [ "$fact_service|$fact_status|$fact_running|$fact_paused|$fact_restarting" = \
    "execution-redis|running|true|false|false" ] || {
      echo "execution Redis 必须是权威 project 中唯一运行实例" >&2
      exit 1
    }
}

require_unique_compose_service_instance() {
  expected_container="$1"
  expected_service="$2"
  expected_status="$3"
  expected_running="$4"
  display_name="$5"
  if service_containers="$(
    docker ps -a -q --no-trunc \
      --filter "label=com.docker.compose.project=$authoritative_project" \
      --filter "label=com.docker.compose.service=$expected_service"
  )"; then
    :
  else
    echo "无法枚举权威 project 的 ${display_name} 容器" >&2
    exit 1
  fi
  set -- $service_containers
  [ "$#" -eq 1 ] || {
    echo "权威 project 的 ${display_name} 容器必须恰有一个且无残留实例" >&2
    exit 1
  }
  authoritative_container="$1"
  case "$authoritative_container" in
    ""|*[!A-Za-z0-9_.-]*)
      echo "权威 project 的 ${display_name} 容器身份无效" >&2
      exit 1
      ;;
  esac
  [ "$authoritative_container" = "$expected_container" ] || {
    echo "传入的 ${display_name} 容器不是权威 project 当前唯一实例" >&2
    exit 1
  }

  if container_facts="$(inspect_compose_container_facts "$authoritative_container")"; then
    :
  else
    echo "无法复验权威 project 的 ${display_name} 容器" >&2
    exit 1
  fi
  parse_compose_container_facts "$container_facts"
  [ "$fact_project" = "$authoritative_project" ] \
    && [ "$fact_config_files" = "$authoritative_config_files" ] \
    && [ "$fact_working_dir" = "$authoritative_working_dir" ] \
    && [ "$fact_service" = "$expected_service" ] || {
      echo "${display_name} 容器与 execution Redis 的 Compose project/config 身份不一致" >&2
      exit 1
    }
  [ "$fact_status|$fact_running|$fact_paused|$fact_restarting" = \
    "$expected_status|$expected_running|false|false" ] || {
      echo "${display_name} 容器状态不满足恢复屏障" >&2
      exit 1
    }
}

require_authoritative_compose_quiescence() {
  require_unique_compose_service_instance \
    "$EXECUTION_REDIS_CONTAINER" execution-redis running true "execution Redis"
  require_unique_compose_service_instance \
    "$CORE_API_CONTAINER" core-api exited false Core
  require_unique_compose_service_instance \
    "$AGENT_SERVICE_CONTAINER" agent-service exited false Agent
}

resolve_authoritative_compose_identity

persistence_info="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-cli --raw INFO persistence
)"
printf '%s\n' "$persistence_info" | grep -q '^aof_enabled:1' || {
  echo "execution Redis 未启用 AOF，拒绝准备 PostgreSQL restore" >&2
  exit 1
}
printf '%s\n' "$persistence_info" | grep -q '^aof_last_write_status:ok' || {
  echo "execution Redis AOF 写状态异常，拒绝准备 PostgreSQL restore" >&2
  exit 1
}

# 这是 PostgreSQL restore 写屏障的运维 quiesce 点。必须先通过 docker compose stop
# 等待两个进程退出，令已经开始的 callback HTTP 完成或随连接断开回滚；仅 route-off
# 或逻辑 dispatch flag 都不能证明不存在最后一次 GET -> HTTP 竞态。
require_authoritative_compose_quiescence

quarantine_key="inkforge:executions:restore:quarantine"
marker="epoch=${RESTORE_EPOCH};snapshotSha256=${database_sha256}"
marker_result="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" redis-cli --raw EVAL \
    "local current = redis.call('GET', KEYS[1]); if current and current ~= ARGV[1] then return -1 end; if not current then redis.call('SET', KEYS[1], ARGV[1]) end; return 1" \
    1 "$quarantine_key" "$marker"
)"
[ "$marker_result" = "1" ] || {
  echo "execution Redis 已有不同恢复隔离身份，拒绝覆盖" >&2
  exit 1
}

waitaof_output="$(
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-cli --raw WAITAOF 1 0 5000
)"
local_aof_ack="$(printf '%s\n' "$waitaof_output" | sed -n '1p' | tr -d '\r')"
[ "$local_aof_ack" = "1" ] || {
  echo "PostgreSQL restore quarantine 未取得本地 AOF 确认，禁止恢复数据库" >&2
  exit 1
}
docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
  redis-cli --raw INFO persistence | grep -q '^aof_last_write_status:ok'

# marker 已耐久后即使服务被误启动也会 fail closed；仍以权威 project 全量枚举复验，拒绝把旧 stopped ID、
# 新启动实例或跨 config 残留宣称为可恢复状态。
require_authoritative_compose_quiescence

echo "PostgreSQL restore 前置 quiesce + execution quarantine 屏障已耐久生效"
echo "数据库恢复完成前 Core 与 Agent 必须保持停止"
echo "恢复完成后只能按 Runbook 在 route-off 且 quarantine 保留时启动对账所需服务"
echo "本脚本不执行数据库覆盖恢复；仍需另行具名授权和联合对账"
