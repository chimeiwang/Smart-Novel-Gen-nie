#!/bin/sh
set -eu
umask 077

stage="${1:-}"
target_database="${2:-}"
app_dir="${APP_DIR:-$(pwd)}"
env_file="${DURABLE_AGENT_MIGRATION_ENV_FILE:-$app_dir/.env}"
compose_file="$app_dir/infra/compose.yaml"
migration_helper="$app_dir/scripts/durable-agent-execution-migration.sh"
image_verifier="$app_dir/scripts/verify-durable-agent-v2-image.sh"
execution_manifest_path="$app_dir/contracts/agent-execution/manifest.json"

case "$stage" in
  pre-contract|post-contract-route-off|schema-ready-route-off|allowlist|route-off-drain|ddl-rollback) ;;
  *) echo "耐久 Agent 发布门禁阶段无效" >&2; exit 2 ;;
esac
case "$target_database" in
  novelwriterdev|novelwriter) ;;
  *) echo "耐久 Agent 发布目标必须精确指定 novelwriterdev 或 novelwriter" >&2; exit 2 ;;
esac
[ -r "$env_file" ] || { echo "发布环境文件不可读" >&2; exit 1; }
[ -r "$compose_file" ] || { echo "生产 Compose 文件不可读" >&2; exit 1; }
[ -r "$migration_helper" ] || { echo "耐久 Agent 迁移 helper 不可读" >&2; exit 1; }
for command_name in docker python3; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "耐久 Agent 发布门禁缺少必要命令：$command_name" >&2
    exit 1
  }
done
docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

execution_manifest_fingerprint() {
  manifest_path="$1"
  python3 - "$manifest_path" <<'PY'
import hashlib
import json
import sys
from pathlib import Path


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"execution manifest 存在重复 key：{key}")
        result[key] = value
    return result


def canonical(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("execution manifest 含未配对 Unicode 代理字符")
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{canonical(key)}:{canonical(value[key])}" for key in sorted(value)
        ) + "}"
    raise ValueError(f"execution manifest 含不支持的值类型：{type(value).__name__}")


document = json.loads(
    Path(sys.argv[1]).read_text(encoding="utf-8"),
    object_pairs_hook=unique_object,
)
if not isinstance(document, dict):
    raise ValueError("execution manifest 顶层必须是对象")
print(hashlib.sha256(canonical(document).encode("utf-8")).hexdigest())
PY
}

read_rollout_config() {
  python3 - "$env_file" <<'PY'
import sys
from pathlib import Path

allowed = {
    "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
    "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
    "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST",
    "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST",
}
values: dict[str, str] = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in allowed:
        continue
    if key in values:
        print("rollout-config:duplicate", file=sys.stderr)
        raise SystemExit(1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    values[key] = value
schema_ready = values.get("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "false").lower()
route_mode = values.get("DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off").lower()
user_allowlist = values.get("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", "").strip()
novel_allowlist = values.get("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", "").strip()
if schema_ready not in {"true", "false"} or route_mode not in {
    "off", "allowlist", "all"
}:
    print("rollout-config:invalid", file=sys.stderr)
    raise SystemExit(1)
print(schema_ready)
print(route_mode)
print("present" if user_allowlist else "absent")
print("present" if novel_allowlist else "absent")
PY
}

config="$(read_rollout_config)" || { echo "耐久 Agent 发布配置无法安全解析" >&2; exit 1; }
schema_ready="$(printf '%s\n' "$config" | sed -n '1p')"
route_mode="$(printf '%s\n' "$config" | sed -n '2p')"
user_allowlist="$(printf '%s\n' "$config" | sed -n '3p')"
novel_allowlist="$(printf '%s\n' "$config" | sed -n '4p')"

migration_state="$(
  APP_DIR="$app_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$env_file" \
    sh "$migration_helper" status "$target_database"
)" || { echo "无法读取耐久 Agent 数据库状态" >&2; exit 1; }
[ "$migration_state" != "partial" ] || {
  echo "耐久 Agent schema 处于 partial drift，所有发布阶段均 fail closed" >&2
  exit 1
}

require_config() {
  expected_schema_ready=$1
  expected_route_mode=$2
  [ "$schema_ready" = "$expected_schema_ready" ] && [ "$route_mode" = "$expected_route_mode" ] || {
    echo "当前 schemaReady/route 组合不符合发布阶段" >&2
    exit 1
  }
}

require_compatible_core() {
  compose exec -T core-api /bin/sh -ec \
    "grep -aFq 'pre-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
     grep -aFq 'post-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
     grep -aFq 'DurableAgentSchemaGate.class' /app/inkforge-core-api.jar" >/dev/null || {
      echo "当前 Core 不是双 contract 兼容镜像" >&2
      exit 1
    }
}

require_v2_aware_images() {
  require_compatible_core
  compose exec -T core-api /bin/sh -ec \
    "grep -aFq 'WorkflowsController.class' /app/inkforge-core-api.jar && \
     grep -aFq 'JooqWorkflowCallbackRepository.class' /app/inkforge-core-api.jar" >/dev/null || {
      echo "当前 Core 镜像不能收敛耐久 Agent V2 Run" >&2
      exit 1
    }
  [ -r "$image_verifier" ] || {
    echo "缺少 V2-aware 镜像检查器" >&2
    exit 1
  }
  running_agent_container="$(compose ps -q agent-service)"
  case "$running_agent_container" in
    ""|*[!A-Za-z0-9_.:-]*)
      echo "无法唯一解析当前 Agent 容器" >&2
      exit 1
      ;;
  esac
  running_agent_image="$(
    docker inspect --format '{{.Image}}' "$running_agent_container"
  )" || {
    echo "无法读取当前 Agent 镜像 ID" >&2
    exit 1
  }
  case "$running_agent_image" in
    sha256:*) running_agent_image_digest="${running_agent_image#sha256:}" ;;
    *)
      echo "当前 Agent 镜像 ID 格式无效" >&2
      exit 1
      ;;
  esac
  case "$running_agent_image_digest" in
    ""|*[!0-9a-f]*)
      echo "当前 Agent 镜像 ID 格式无效" >&2
      exit 1
      ;;
  esac
  [ "${#running_agent_image_digest}" -eq 64 ] || {
    echo "当前 Agent 镜像 ID 格式无效" >&2
    exit 1
  }
  if agent_probe="$(sh "$image_verifier" agent "$running_agent_image")"; then
    :
  else
    echo "当前 Agent 镜像无法离线验证 execution manifest" >&2
    exit 1
  fi
  case "$agent_probe" in
    v2-aware-image-ok:agent:*)
      current_agent_manifest_fingerprint="${agent_probe#v2-aware-image-ok:agent:}"
      ;;
    *)
      echo "当前 Agent 镜像探针输出格式无效" >&2
      exit 1
      ;;
  esac
  case "$current_agent_manifest_fingerprint" in
    *[!0-9a-f]*)
      echo "当前 Agent 镜像输出了无效的 execution manifest 指纹" >&2
      exit 1
      ;;
  esac
  [ "${#current_agent_manifest_fingerprint}" -eq 64 ] || {
    echo "当前 Agent 镜像输出了无效的 execution manifest 指纹" >&2
    exit 1
  }
}

load_release_execution_manifest() {
  [ -r "$execution_manifest_path" ] || {
    echo "缺少当前发布的冻结 execution manifest" >&2
    exit 1
  }
  if expected_execution_manifest_fingerprint="$(
    execution_manifest_fingerprint "$execution_manifest_path"
  )"; then
    :
  else
    echo "无法计算当前发布的冻结 execution manifest 指纹" >&2
    exit 1
  fi
  case "$expected_execution_manifest_fingerprint" in
    *[!0-9a-f]*)
      echo "当前发布的 execution manifest 指纹无效" >&2
      exit 1
      ;;
  esac
  [ "${#expected_execution_manifest_fingerprint}" -eq 64 ] || {
    echo "当前发布的 execution manifest 指纹无效" >&2
    exit 1
  }
}

require_release_execution_manifest() {
  load_release_execution_manifest
  [ "$current_agent_manifest_fingerprint" = \
    "$expected_execution_manifest_fingerprint" ] || {
      echo "allowlist Agent 与当前发布冻结 execution manifest 不一致" >&2
      exit 1
    }
}

require_route_off_execution_manifest() {
  load_release_execution_manifest
  [ "$current_agent_manifest_fingerprint" != \
    "$expected_execution_manifest_fingerprint" ] || return 0

  compose exec -T core-api /bin/sh -ec \
    'test "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-}" = off' || {
      echo "当前运行 Core 未精确证明 route=off" >&2
      exit 1
    }
  active_v2_run_count="$(
    APP_DIR="$app_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$env_file" \
      sh "$migration_helper" active-v2-count "$target_database"
  )" || {
    echo "无法从权威 PostgreSQL 读取 V2 非终态 Run 数量" >&2
    exit 1
  }
  case "$active_v2_run_count" in
    ""|*[!0-9]*)
      echo "权威 PostgreSQL 返回了无效的 V2 非终态 Run 数量" >&2
      exit 1
      ;;
  esac
  [ "$active_v2_run_count" = "0" ] || {
    echo "仍有 V2 非终态 Run，route-off 不允许使用不同 execution manifest" >&2
    exit 1
  }
}

require_exact_contract() {
  compose exec -T core-api /usr/local/bin/inkforge-schema-guard >/dev/null || {
    echo "实时 PostgreSQL 未精确命中兼容镜像内任一冻结 contract" >&2
    exit 1
  }
}

require_services_ready() {
  compose exec -T core-api curl --fail --silent --show-error \
    http://127.0.0.1:8000/api/v1/health/ready >/dev/null || {
      echo "Core readiness 未通过" >&2
      exit 1
    }
  compose exec -T agent-service python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/internal/v1/health/ready', timeout=3).read()" \
    >/dev/null || {
      echo "Agent readiness 未通过" >&2
      exit 1
    }
}

require_execution_journal_ready() {
  persistence_info="$(compose exec -T execution-redis redis-cli --raw INFO persistence)"
  printf '%s\n' "$persistence_info" | grep -q '^aof_enabled:1' || {
    echo "execution Redis 未启用 AOF" >&2
    exit 1
  }
  printf '%s\n' "$persistence_info" | grep -q '^aof_last_write_status:ok' || {
    echo "execution Redis AOF 写状态异常" >&2
    exit 1
  }
  quarantine_exists="$(compose exec -T execution-redis redis-cli --raw EXISTS \
    inkforge:executions:restore:quarantine | tr -d '\r')"
  [ "$quarantine_exists" = "0" ] || {
    echo "execution Redis 仍处于 restore quarantine" >&2
    exit 1
  }
  evicted_keys="$(compose exec -T execution-redis redis-cli --raw INFO stats \
    | tr -d '\r' | sed -n 's/^evicted_keys:\([0-9][0-9]*\)$/\1/p')"
  [ "$evicted_keys" = "0" ] || {
    echo "execution Redis 已发生 eviction 或无法证明为零" >&2
    exit 1
  }
}

case "$stage" in
  pre-contract)
    [ "$migration_state" = "unmigrated" ] || {
      echo "pre-contract 阶段必须仍为完整迁移前结构" >&2
      exit 1
    }
    require_config false off
    require_v2_aware_images
    require_exact_contract
    require_services_ready
    require_execution_journal_ready
    ;;
  post-contract-route-off)
    [ "$migration_state" = "migrated-empty-v2" ] || {
      echo "在线迁移后首次门禁必须是完整、空 V2 结构" >&2
      exit 1
    }
    require_config false off
    require_v2_aware_images
    require_route_off_execution_manifest
    require_exact_contract
    require_services_ready
    require_execution_journal_ready
    ;;
  schema-ready-route-off)
    [ "$migration_state" = "migrated-empty-v2" ] || {
      echo "schema-ready 首次重启前不得已有 V2 数据" >&2
      exit 1
    }
    require_config true off
    require_v2_aware_images
    require_route_off_execution_manifest
    require_exact_contract
    require_services_ready
    require_execution_journal_ready
    ;;
  allowlist)
    case "$migration_state" in migrated-empty-v2|migrated-with-v2) ;; *) exit 1 ;; esac
    require_config true allowlist
    [ "$user_allowlist" = "present" ] && [ "$novel_allowlist" = "present" ] || {
      echo "allowlist 阶段必须同时配置用户与隔离小说 ID" >&2
      exit 1
    }
    require_v2_aware_images
    require_release_execution_manifest
    require_exact_contract
    require_services_ready
    require_execution_journal_ready
    ;;
  route-off-drain)
    case "$migration_state" in migrated-empty-v2|migrated-with-v2) ;; *) exit 1 ;; esac
    require_config true off
    require_v2_aware_images
    require_route_off_execution_manifest
    require_exact_contract
    require_services_ready
    require_execution_journal_ready
    ;;
  ddl-rollback)
    [ "$migration_state" = "migrated-empty-v2" ] || {
      echo "DDL rollback 只允许完整迁移后且 V2 数据为空" >&2
      exit 1
    }
    require_config false off
    require_compatible_core
    require_exact_contract
    require_execution_journal_ready
    ;;
esac

printf 'gate-ok:%s:%s\n' "$stage" "$migration_state"
