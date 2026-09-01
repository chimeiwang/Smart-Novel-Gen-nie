#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"
REPO_URL="${REPO_URL:-https://github.com/chimeiwang/Smart-Novel-Gen-nie.git}"
BRANCH="${BRANCH:-main}"
DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"
DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:?必须设置部署源码 bundle}"
INKFORGE_IMAGE_TAG="${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
control_dir="${DURABLE_AGENT_CONTROL_BUNDLE_DIR:?必须设置不可变 control bundle 目录}"
control_bundle_sha="${DURABLE_AGENT_CONTROL_BUNDLE_SHA256:?必须设置 control bundle SHA-256}"
control_bundle_verifier="$control_dir/scripts/durable_agent_v2_control_bundle.py"
compose_file="$control_dir/infra/compose.yaml"
python_rollback_file="$control_dir/infra/compose.python-core-rollback.yaml"
release_guard_compose_file="$control_dir/infra/compose.durable-agent-release-guard.yaml"
durable_migration_helper="$control_dir/scripts/durable-agent-execution-migration.sh"
durable_image_verifier="$control_dir/scripts/verify-durable-agent-v2-image.sh"
durable_release_driver="$control_dir/scripts/durable-agent-v2-release.sh"
execution_manifest_path="$control_dir/contracts/agent-execution/manifest.json"
durable_release_manifest_dir="${DURABLE_AGENT_RELEASE_MANIFEST_DIR:?必须设置 release manifest 目录}"
durable_release_operation="${DURABLE_AGENT_RELEASE_OPERATION:?必须设置 release manifest 动作}"
workflow_trusted_commit="${WORKFLOW_TRUSTED_COMMIT:?必须设置 workflow trusted commit}"
target_release_commit="${TARGET_RELEASE_COMMIT:?必须设置 target release commit}"
release_manifest_sha256="${RELEASE_MANIFEST_SHA256:?必须设置 release manifest SHA-256}"
release_action="${RELEASE_ACTION:?必须设置 release action}"
deploy_runtime_route_mode="${DEPLOY_RUNTIME_ROUTE_MODE:?必须设置部署阶段 route mode}"
release_lock_id="${DURABLE_AGENT_RELEASE_LOCK_ID:?必须设置 release transaction lock ID}"
release_lock_file="$APP_DIR/.durable-agent-v2-release-transaction.lock"
release_lock_dir="$APP_DIR/.durable-agent-v2-release-transactions/$release_lock_id"
release_lock_owner="$release_lock_dir/owner"
release_guard_root="$APP_DIR/.durable-agent-v2-release-guard"
DURABLE_AGENT_RELEASE_GUARD_HOST_DIR="$release_guard_root"
export DURABLE_AGENT_RELEASE_GUARD_HOST_DIR

case "$durable_release_operation" in release|rollback) ;;
  *) echo "受保护发布动作必须是 release 或 rollback" >&2; exit 1 ;;
esac
case "$release_action" in route_off_release|allowlist_release|rollback) ;;
  *) echo "release action 无效" >&2; exit 1 ;;
esac
case "$deploy_runtime_route_mode" in off) ;;
  *) echo "受保护部署阶段必须保持 route-off" >&2; exit 1 ;;
esac
if [ "$durable_release_operation" = rollback ]; then
  [ "$release_action" = rollback ] || {
    echo "rollback 操作与 release action 不一致" >&2
    exit 1
  }
else
  [ "$release_action" != rollback ] || {
    echo "release 操作与 release action 不一致" >&2
    exit 1
  }
fi
for value in "$workflow_trusted_commit" "$target_release_commit" "$DEPLOY_SHA"; do
  case "$value" in ""|*[!0-9a-f]*) echo "发布提交格式无效" >&2; exit 1 ;; esac
  [ "${#value}" -eq 40 ] || { echo "发布提交格式无效" >&2; exit 1; }
done
for value in "$release_manifest_sha256" "$release_lock_id" "$control_bundle_sha"; do
  case "$value" in ""|*[!0-9a-f]*) echo "发布 SHA 格式无效" >&2; exit 1 ;; esac
  [ "${#value}" -eq 64 ] || { echo "发布 SHA 格式无效" >&2; exit 1; }
done
control_output="$(python3 "$control_bundle_verifier" verify \
  --bundle-dir "$control_dir" --expected-sha256 "$control_bundle_sha")" || {
    echo "不可变 control bundle 复验失败" >&2
    exit 1
  }
[ "$control_output" = "control-bundle-verified:$control_bundle_sha" ] || exit 1
[ "${GITHUB_ACTIONS:-}" = "true" ] \
  && [ "${GITHUB_EVENT_NAME:-}" = "workflow_dispatch" ] \
  && [ "${GITHUB_REF:-}" = "refs/heads/main" ] \
  && [ "${GITHUB_SHA:-}" = "$workflow_trusted_commit" ] \
  && [ "${INKFORGE_RELEASE_APPROVED_ENVIRONMENT:-}" = "production" ] || {
    echo "受保护发布缺少 GitHub production environment 审批上下文" >&2
    exit 1
  }
case "${GITHUB_RUN_ID:-}" in ""|0|*[!0-9]*) echo "GitHub run ID 无效" >&2; exit 1 ;; esac
case "${GITHUB_RUN_ATTEMPT:-}" in ""|0|*[!0-9]*) echo "GitHub run attempt 无效" >&2; exit 1 ;; esac

# GitHub concurrency 只能减少并发；服务器固定目录的原子锁才是跨旧 Workflow 的最终互斥事实。
python3 - "$release_lock_file" "$release_lock_id" "$GITHUB_RUN_ID" \
  "$GITHUB_RUN_ATTEMPT" "$release_action" "$workflow_trusted_commit" \
  "$target_release_commit" "$control_bundle_sha" "$release_lock_dir" <<'PY'
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
    raise SystemExit("release-lock-file")
expected = {
    "format": "2",
    "lockId": sys.argv[2],
    "runId": sys.argv[3],
    "runAttempt": sys.argv[4],
    "operation": sys.argv[5],
    "workflowTrustedCommit": sys.argv[6],
    "targetReleaseCommit": sys.argv[7],
    "controlBundleSha256": sys.argv[8],
}
actual = {}
for raw in path.read_text(encoding="ascii").splitlines():
    if raw.count("=") != 1:
        raise SystemExit("release-lock-format")
    key, value = raw.split("=", 1)
    if key in actual:
        raise SystemExit("release-lock-duplicate")
    actual[key] = value
if actual != expected:
    raise SystemExit("release-lock-owner")
state_root = Path(sys.argv[9])
owner = state_root / "owner"
state = state_root / "state"
if state.read_text(encoding="ascii") != "active\n" or not owner.samefile(path):
    raise SystemExit("release-lock-state")
PY

cleanup_deploy_bundle() {
  [ -z "$DEPLOY_BUNDLE_PATH" ] || rm -f -- "$DEPLOY_BUNDLE_PATH"
}

cleanup_deploy_bundle_on_exit() {
  cleanup_original_status="$1"
  trap - EXIT HUP INT TERM
  cleanup_deploy_bundle || echo "部署源码 bundle 清理失败" >&2
  exit "$cleanup_original_status"
}

if [ -n "$DEPLOY_BUNDLE_PATH" ]; then
  case "$DEPLOY_SHA" in
    ""|*[!0-9a-f]*)
      echo "使用 bundle 部署时，部署提交必须是 40 位小写十六进制 SHA" >&2
      exit 1
      ;;
  esac
  [ "${#DEPLOY_SHA}" -eq 40 ] || {
    echo "使用 bundle 部署时，部署提交必须是 40 位小写十六进制 SHA" >&2
    exit 1
  }
  expected_bundle_path="/tmp/inkforge-deploy-${DEPLOY_SHA}.bundle"
  [ "$DEPLOY_BUNDLE_PATH" = "$expected_bundle_path" ] || {
    echo "部署源码 bundle 路径不符合提交绑定约定" >&2
    exit 1
  }
  trap 'cleanup_deploy_bundle_on_exit "$?"' EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
  [ -f "$DEPLOY_BUNDLE_PATH" ] && [ -r "$DEPLOY_BUNDLE_PATH" ] || {
    echo "部署源码 bundle 不存在或不可读" >&2
    exit 1
  }
fi

# Java 与历史 Python Core 使用不同的回滚覆盖层；运行时分类必须来自镜像标签，不能靠版本号猜测。
compose() {
  docker compose --env-file "$APP_DIR/.env" --project-directory "$control_dir/infra" \
    -f "$compose_file" -f "$release_guard_compose_file" "$@"
}

compose_python_rollback() {
  docker compose --env-file "$APP_DIR/.env" --project-directory "$control_dir/infra" \
    -f "$compose_file" -f "$release_guard_compose_file" \
    -f "$python_rollback_file" "$@"
}

# Compose 配置和 Redis/Nginx 配置来自不可变 control bundle；服务密钥仍是服务器受保护数据，
# 显式使用绝对路径，避免 --project-directory 改变相对路径解析后误读 bundle 或旧 checkout。
SERVICE_KEYS_DIR="$APP_DIR/infra/secrets"
export SERVICE_KEYS_DIR

initialize_persistent_volume() {
  volume_name="$1"
  mount_path="$2"
  image="$3"
  owner="$4"
  chown_path="$5"

  docker volume create "$volume_name" >/dev/null
  docker run \
    --rm \
    --network none \
    --read-only \
    --cap-drop ALL \
    --cap-add CHOWN \
    --user 0:0 \
    --mount "type=volume,source=$volume_name,target=$mount_path" \
    --entrypoint "$chown_path" \
    "$image" \
    "$owner" "$mount_path"
}

initialize_persistent_volumes() {
  # 只调整卷根目录，不递归触碰已有上传、日志或 execution AOF 数据。
  initialize_persistent_volume \
    inkforge_uploads /data/uploads "inkforge-core-api:$INKFORGE_IMAGE_TAG" \
    10001:10001 /usr/bin/chown
  initialize_persistent_volume \
    inkforge_agent_logs /data/agent-logs "inkforge-agent-service:$INKFORGE_IMAGE_TAG" \
    10001:10001 /usr/bin/chown
  initialize_persistent_volume \
    inkforge_execution_redis_data /data redis:7.4-alpine \
    999:999 /bin/chown
}

refresh_nginx() {
  compose up --no-build -d --wait --no-deps --force-recreate nginx
}

find_service_container() {
  service="$1"
  docker ps -q \
    --filter "label=com.docker.compose.project=inkforge" \
    --filter "label=com.docker.compose.service=$service" \
    | head -n 1
}

verify_running_core_rollout_config() {
  container_id="$1"
  expected_route="$2"
  expected_scope_sha256="$3"
  expected_v1_fresh_starts="$4"
  raw="$(docker exec "$container_id" /bin/sh -ec \
    'printf "%s\n%s\n%s\n%s\n%s\n" "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-off}" "${DURABLE_AGENT_EXECUTION_SCHEMA_READY:-false}" "${DURABLE_AGENT_EXECUTION_USER_ALLOWLIST:-}" "${DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST:-}" "${V1_FRESH_AGENT_STARTS_ENABLED:-true}"')" || {
      echo "无法读取运行 Core 的耐久 Agent 配置" >&2
      return 1
    }
  route="$(printf '%s\n' "$raw" | sed -n '1p')"
  schema_ready="$(printf '%s\n' "$raw" | sed -n '2p')"
  user_id="$(printf '%s\n' "$raw" | sed -n '3p')"
  novel_id="$(printf '%s\n' "$raw" | sed -n '4p')"
  v1_fresh_starts="$(printf '%s\n' "$raw" | sed -n '5p')"
  [ "$(printf '%s\n' "$raw" | wc -l | tr -d ' ')" = 5 ] \
    && [ "$route" = "$expected_route" ] || {
      echo "运行 Core 的 route 配置发生漂移" >&2
      return 1
    }
  case "$schema_ready" in true|false) ;;
    *) echo "运行 Core 的 schemaReady 无效" >&2; return 1 ;;
  esac
  case "$v1_fresh_starts" in true|false) ;;
    *) echo "运行 Core 的 V1 fresh start 配置无效" >&2; return 1 ;;
  esac
  [ "$expected_v1_fresh_starts" = any ] \
    || [ "$v1_fresh_starts" = "$expected_v1_fresh_starts" ] || {
      echo "运行 Core 的 V1 fresh start 配置发生漂移" >&2
      return 1
    }
  [ "$v1_fresh_starts" != false ] \
    || docker exec "$container_id" /bin/sh -ec \
      'grep -aFq "V1FreshAgentStartGate.class" /app/inkforge-core-api.jar' || {
        echo "运行 Core 声明关闭 V1 fresh start 但镜像不含门禁实现" >&2
        return 1
      }
  [ "$route" != allowlist ] || [ "$schema_ready" = true ] || {
    echo "运行 Core 的 allowlist 未启用 schemaReady" >&2
    return 1
  }
  actual_scope_sha256="$(python3 - "$user_id" "$novel_id" <<'PY'
import hashlib
import json
import re
import sys

pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
user_id, novel_id = sys.argv[1:]
if not pattern.fullmatch(user_id) or not pattern.fullmatch(novel_id):
    raise SystemExit("scope-id")
payload = json.dumps(
    {"novelId": novel_id, "userId": user_id},
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode()
print(hashlib.sha256(payload).hexdigest())
PY
)" || return 1
  [ "$actual_scope_sha256" = "$expected_scope_sha256" ] || {
    echo "运行 Core 的 canary scope 发生漂移" >&2
    return 1
  }
}

safe_git() {
  git -c safe.directory="$APP_DIR" "$@"
}

read_release_manifest_field() {
  python3 - "$durable_release_manifest_dir" "$release_manifest_sha256" \
    "$target_release_commit" "$1" <<'PY'
import hashlib
import json
import stat
import sys
from pathlib import Path

directory = Path(sys.argv[1])
expected_sha = sys.argv[2]
expected_target = sys.argv[3]
field = sys.argv[4]
paths = {
    "canary-scope-sha256": ("canaryScopeSha256",),
    "development-evidence-sha256": ("developmentEvidenceSha256",),
    "control-bundle-sha256": ("controlBundleSha256",),
    "workflow-trusted-commit": ("workflowTrustedCommit",),
    "target-release-commit": ("targetReleaseCommit",),
    "rollback-source-release-commit": ("rollbackSourceReleaseCommit",),
    "rollback-source-receipt-sha256": ("rollbackSourceReceiptSha256",),
    "route-mode": ("routeMode",),
    "source-manifest-fingerprint": ("executionManifestFingerprints", "source"),
    "target-manifest-fingerprint": ("executionManifestFingerprints", "target"),
    "rollback-manifest-fingerprint": ("executionManifestFingerprints", "rollback"),
    "target-web-digest": ("images", "target", "web"),
    "target-core-digest": ("images", "target", "core"),
    "target-agent-digest": ("images", "target", "agent"),
    "rollback-web-digest": ("images", "rollback", "web"),
    "rollback-core-digest": ("images", "rollback", "core"),
    "rollback-agent-digest": ("images", "rollback", "agent"),
}

if field not in paths or directory.is_symlink() or not directory.is_dir():
    raise SystemExit("release-manifest-path")
manifest = directory / "release-manifest.json"
checksums = directory / "SHA256SUMS"
if {path.name for path in directory.iterdir()} != {manifest.name, checksums.name}:
    raise SystemExit("release-manifest-files")
for path in (manifest, checksums):
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit("release-manifest-file")

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

payload = manifest.read_bytes()
actual_sha = hashlib.sha256(payload).hexdigest()
if actual_sha != expected_sha or checksums.read_text(encoding="ascii") != (
    f"{actual_sha}  release-manifest.json\n"
):
    raise SystemExit("release-manifest-sha")
document = json.loads(payload.decode("utf-8"), object_pairs_hook=unique)
canonical = (
    json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n"
).encode()
if payload != canonical or document.get("format") != "inkforge-durable-agent-v2-release/3":
    raise SystemExit("release-manifest-canonical")
if document.get("targetReleaseCommit") != expected_target:
    raise SystemExit("release-manifest-target")
value = document
for key in paths[field]:
    value = value[key]
if not isinstance(value, str):
    raise SystemExit("release-manifest-field")
print(value)
PY
}

verify_verified_drain_evidence() {
  APP_DIR="$APP_DIR" DURABLE_AGENT_CONTROL_BUNDLE_DIR="$control_dir" \
    DURABLE_AGENT_CONTROL_BUNDLE_SHA256="$control_bundle_sha" \
    sh "$control_dir/scripts/durable-agent-v2-release.sh" \
      verify-drain-binding >/dev/null || {
        echo "verifiedDrain 不能由当前不可变 control bundle 复验" >&2
        return 1
      }
}

require_release_image_digest() {
  component="$1"
  digest="$2"
  repository="inkforge-$component"
  [ "$component" != "core" ] || repository="inkforge-core-api"
  [ "$component" != "agent" ] || repository="inkforge-agent-service"
  case "$digest" in sha256:*) digest_hex="${digest#sha256:}" ;;
    *) echo "release manifest 镜像 digest 格式无效：$component" >&2; exit 1 ;;
  esac
  case "$digest_hex" in ""|*[!0-9a-f]*)
    echo "release manifest 镜像 digest 格式无效：$component" >&2
    exit 1
    ;;
  esac
  [ "${#digest_hex}" -eq 64 ] || {
    echo "release manifest 镜像 digest 格式无效：$component" >&2
    exit 1
  }
  actual_digest="$(docker image inspect --format '{{.Id}}' "$digest")" || {
    echo "release manifest 冻结镜像不存在：$component" >&2
    exit 1
  }
  [ "$actual_digest" = "$digest" ] || {
    echo "release manifest 冻结镜像发生漂移：$component" >&2
    exit 1
  }
  docker image tag "$digest" "$repository:$INKFORGE_IMAGE_TAG" >/dev/null
  tagged_digest="$(docker image inspect --format '{{.Id}}' \
    "$repository:$INKFORGE_IMAGE_TAG")"
  [ "$tagged_digest" = "$digest" ] || {
    echo "release manifest 镜像临时标签未绑定冻结 digest：$component" >&2
    exit 1
  }
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

verify_java_stack() {
  compose ps &&
  compose exec -T core-api /usr/local/bin/inkforge-schema-guard &&
  (cd "$control_dir" && COMPOSE_ENV_FILE="$APP_DIR/.env" COMPOSE_OVERRIDE_FILE= \
    COMPOSE_ADDITIONAL_OVERRIDE_FILE="$release_guard_compose_file" \
    sh scripts/compose_smoke.sh)
}

verify_python_rollback_stack() {
  compose_python_rollback ps &&
  compose_python_rollback exec -T core-api python -c \
    'import asyncio, os; from inkforge_core.config import Settings; from inkforge_core.db.schema_guard import verify_live_schema; from inkforge_core.db.session import SCHEMA_CONTRACT_PATH, schema_profile_for_settings; settings = Settings(); result = asyncio.run(verify_live_schema(os.environ["DATABASE_URL"], SCHEMA_CONTRACT_PATH, profile=schema_profile_for_settings(settings))); print(result.fingerprint); raise SystemExit(0 if result.ready else 1)' &&
  (cd "$control_dir" && COMPOSE_ENV_FILE="$APP_DIR/.env" \
    COMPOSE_OVERRIDE_FILE="$python_rollback_file" \
    COMPOSE_ADDITIONAL_OVERRIDE_FILE="$release_guard_compose_file" \
    sh scripts/compose_smoke.sh)
}

core_image_runtime_label() {
  docker image inspect \
    --format '{{ index .Config.Labels "cn.inkforge.core.runtime" }}' "$1"
}

classify_core_runtime() {
  case "$1" in
    java) printf '%s\n' java ;;
    ""|"<no value>") printf '%s\n' python ;;
    *) printf '%s\n' unknown ;;
  esac
}

snapshot_running_service_image() {
  service_name="$1"
  expected_repository="$2"
  container_id="$3"
  rollback_tag="$4"

  if declared_image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"; then
    :
  else
    echo "无法读取 $service_name 容器声明镜像" >&2
    return 1
  fi
  # Config.Image 只用于校验服务归属；回滚来源必须使用容器实际绑定的不可变 Image ID。
  case "$declared_image" in
    "$expected_repository":*) ;;
    *)
      echo "$service_name 容器镜像仓库不符合生产约定" >&2
      return 1
      ;;
  esac

  if running_image_id="$(docker inspect --format '{{.Image}}' "$container_id")"; then
    :
  else
    echo "无法读取 $service_name 容器实际镜像 ID" >&2
    return 1
  fi
  case "$running_image_id" in
    sha256:*) ;;
    *)
      echo "$service_name 容器实际镜像 ID 格式无效" >&2
      return 1
      ;;
  esac

  if canonical_image_id="$(docker image inspect --format '{{.Id}}' "$running_image_id")"; then
    :
  else
    echo "现有生产镜像已缺失或不可读取：$service_name" >&2
    return 1
  fi
  [ "$canonical_image_id" = "$running_image_id" ] || {
    echo "$service_name 容器镜像 ID 与本机镜像不一致" >&2
    return 1
  }

  rollback_image="$expected_repository:$rollback_tag"
  # 同一提交的回滚标签一旦建立就不允许改指，避免人工重跑覆盖仍需保留的恢复点。
  if existing_snapshot_id="$(
    docker image inspect --format '{{.Id}}' "$rollback_image" 2>/dev/null
  )"; then
    [ "$existing_snapshot_id" = "$running_image_id" ] || {
      echo "$service_name 回滚镜像标签已存在但指向另一镜像" >&2
      return 1
    }
  else
    # image tag 只增加本地别名，不复制镜像层，也不会重建或停止当前生产容器。
    docker image tag "$running_image_id" "$rollback_image" >/dev/null || {
      echo "无法创建 $service_name 回滚镜像标签" >&2
      return 1
    }
  fi
  if snapshotted_image_id="$(docker image inspect --format '{{.Id}}' "$rollback_image")"; then
    :
  else
    echo "无法反查 $service_name 回滚镜像标签" >&2
    return 1
  fi
  [ "$snapshotted_image_id" = "$running_image_id" ] || {
    echo "$service_name 回滚镜像标签未指向当前运行镜像" >&2
    return 1
  }

  printf '%s\n' "$running_image_id"
}

command -v docker >/dev/null 2>&1 || { echo "缺少 docker 命令" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "缺少 git 命令" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "缺少 python3 命令" >&2; exit 1; }

# APP_DIR 和 release lock 已由 begin transaction 确认；部署入口不能创建新的无锁服务器状态。
cd "$APP_DIR"

manifest_workflow_commit="$(read_release_manifest_field workflow-trusted-commit)"
manifest_target_commit="$(read_release_manifest_field target-release-commit)"
manifest_rollback_source_commit="$(
  read_release_manifest_field rollback-source-release-commit
)"
[ "$manifest_target_commit" = "$target_release_commit" ] || {
  echo "manifest target commit 与受保护上下文不一致" >&2
  exit 1
}
if [ "$durable_release_operation" = release ]; then
  [ "$manifest_workflow_commit" = "$workflow_trusted_commit" ] \
    && [ "$DEPLOY_SHA" = "$manifest_target_commit" ] \
    && [ "$(read_release_manifest_field control-bundle-sha256)" = \
      "$control_bundle_sha" ] || {
      echo "release 源码提交与 manifest 不一致" >&2
      exit 1
    }
else
  [ "$DEPLOY_SHA" = "$manifest_rollback_source_commit" ] || {
    echo "rollback 源码提交与 manifest 不一致" >&2
    exit 1
  }
fi

manifest_target_fingerprint_preflight="$(
  read_release_manifest_field target-manifest-fingerprint
)"
manifest_rollback_fingerprint_preflight="$(
  read_release_manifest_field rollback-manifest-fingerprint
)"
preflight_core_container="$(find_service_container core-api)"
[ -n "$preflight_core_container" ] || {
  echo "verifiedDrain 前置门禁找不到当前 Core" >&2
  exit 1
}
docker exec "$preflight_core_container" /bin/sh -ec \
  'test "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-}" = off && test "${V1_FRESH_AGENT_STARTS_ENABLED:-}" = false' || {
    echo "当前运行 Core 未精确证明 V1/V2 新建入口关闭" >&2
    exit 1
  }
verify_verified_drain_evidence || exit 1

if [ ! -d .git ]; then
  safe_git init -b "$BRANCH"
  safe_git remote add origin "$REPO_URL"
else
  safe_git remote set-url origin "$REPO_URL"
fi

# 受保护部署只信任 runner 已 checkout 并经固定主机身份上传的 bundle；服务器不再保留 fetch 兼容旁路。
safe_git bundle verify "$DEPLOY_BUNDLE_PATH"
safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD
bundle_sha="$(safe_git rev-parse FETCH_HEAD)"
[ "$bundle_sha" = "$DEPLOY_SHA" ] || {
  echo "部署源码 bundle 与部署提交不一致" >&2
  exit 1
}
safe_git update-ref "refs/remotes/origin/$BRANCH" "$DEPLOY_SHA"
remote_sha="$(safe_git rev-parse "refs/remotes/origin/$BRANCH")"
[ "$remote_sha" = "$DEPLOY_SHA" ] || {
  echo "远程分支提交与部署提交不一致" >&2
  exit 1
}
[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
[ -r .env ] || { echo "部署用户无法读取 .env" >&2; exit 1; }
[ -r "$durable_migration_helper" ] || { echo "缺少耐久 Agent 具名迁移 helper" >&2; exit 1; }
[ -r "$durable_image_verifier" ] || { echo "缺少 V2-aware 镜像检查器" >&2; exit 1; }
[ -r "$execution_manifest_path" ] || { echo "缺少冻结 execution manifest" >&2; exit 1; }
release_manifest_route_mode=""
release_manifest_source_fingerprint=""
release_manifest_deploy_fingerprint=""
release_manifest_start_web_digest=""
release_manifest_start_core_digest=""
release_manifest_start_agent_digest=""
release_manifest_route_mode="$(read_release_manifest_field route-mode)"
case "$release_action:$release_manifest_route_mode" in
  route_off_release:off|allowlist_release:allowlist|rollback:off|rollback:allowlist) ;;
  *) echo "release action 与 manifest 最终 route 不一致" >&2; exit 1 ;;
esac
release_manifest_source_fingerprint="$(
  read_release_manifest_field source-manifest-fingerprint
)"
if [ "$durable_release_operation" = "release" ]; then
  deploy_image_group="target"
  start_image_group="rollback"
else
  deploy_image_group="rollback"
  start_image_group="target"
fi
deploy_web_digest="$(read_release_manifest_field "$deploy_image_group-web-digest")"
deploy_core_digest="$(read_release_manifest_field "$deploy_image_group-core-digest")"
deploy_agent_digest="$(read_release_manifest_field "$deploy_image_group-agent-digest")"
release_manifest_deploy_fingerprint="$(
  read_release_manifest_field "$deploy_image_group-manifest-fingerprint"
)"
release_manifest_start_web_digest="$(
  read_release_manifest_field "$start_image_group-web-digest"
)"
release_manifest_start_core_digest="$(
  read_release_manifest_field "$start_image_group-core-digest"
)"
release_manifest_start_agent_digest="$(
  read_release_manifest_field "$start_image_group-agent-digest"
)"
case "$INKFORGE_IMAGE_TAG" in
  ""|*[!A-Za-z0-9_.-]*) echo "受保护发布临时镜像标签无效" >&2; exit 1 ;;
esac
# release manifest 的 sha256 digest 是部署权威；标签只在本次 Compose 调用前建立本地别名。
require_release_image_digest web "$deploy_web_digest"
require_release_image_digest core "$deploy_core_digest"
require_release_image_digest agent "$deploy_agent_digest"
# 以下检查都在启动新容器前完成，失败时不得触碰现有生产进程。
grep -q 'host.docker.internal' "$compose_file" || {
  echo "生产编排未配置宿主机数据库网关" >&2
  exit 1
}
grep -Eq '^DATABASE_URL=.*@host\.docker\.internal([:/?]|$)' .env || {
  echo ".env 的 DATABASE_URL 未指向宿主机数据库网关" >&2
  exit 1
}
[ -x infra/secrets ] || { echo "部署用户无法检查服务密钥目录" >&2; exit 1; }
for key_file in \
  core-to-agent-private.pem \
  core-to-agent-jwks.json \
  agent-to-core-private.pem \
  agent-to-core-jwks.json
do
  [ -f "infra/secrets/$key_file" ] || { echo "缺少服务密钥：$key_file" >&2; exit 1; }
done
for private_key in core-to-agent-private.pem agent-to-core-private.pem
do
  owner="$(stat -c %u "infra/secrets/$private_key")"
  group="$(stat -c %g "infra/secrets/$private_key")"
  mode="$(stat -c %a "infra/secrets/$private_key")"
  [ "$owner" = "10001" ] && [ "$group" = "10001" ] && [ "$mode" = "600" ] || {
    echo "服务私钥必须归属容器用户 10001:10001 且权限为 600：$private_key" >&2
    exit 1
  }
done

for image in \
  "inkforge-web:$INKFORGE_IMAGE_TAG" \
  "inkforge-core-api:$INKFORGE_IMAGE_TAG" \
  "inkforge-agent-service:$INKFORGE_IMAGE_TAG"
do
  docker image inspect "$image" >/dev/null 2>&1 || { echo "缺少预构建镜像：$image" >&2; exit 1; }
done
docker image inspect redis:7.4-alpine >/dev/null 2>&1 || {
  echo "缺少固定 Redis 运行镜像：redis:7.4-alpine" >&2
  exit 1
}

if new_core_runtime_label="$(core_image_runtime_label "inkforge-core-api:$INKFORGE_IMAGE_TAG")"; then
  :
else
  echo "无法读取新 Core 镜像 runtime 标签" >&2
  exit 1
fi
[ "$(classify_core_runtime "$new_core_runtime_label")" = "java" ] || {
  echo "新 Core 镜像不是 Java runtime" >&2
  exit 1
}

if source_execution_manifest_fingerprint="$(
  execution_manifest_fingerprint "$execution_manifest_path"
)"; then
  :
else
  echo "无法从发布源码计算冻结 execution manifest 指纹" >&2
  exit 1
fi
case "$source_execution_manifest_fingerprint" in
  *[!0-9a-f]*)
    echo "发布源码产生了无效的 execution manifest 指纹" >&2
    exit 1
    ;;
esac
[ "${#source_execution_manifest_fingerprint}" -eq 64 ] || {
  echo "发布源码产生了无效的 execution manifest 指纹" >&2
  exit 1
}
if [ "$durable_release_operation" = release ]; then
  expected_source_fingerprint="$release_manifest_source_fingerprint"
else
  expected_source_fingerprint="$release_manifest_deploy_fingerprint"
fi
[ "$source_execution_manifest_fingerprint" = "$expected_source_fingerprint" ] || {
  echo "部署源码与 release manifest 的 execution manifest 指纹不一致" >&2
  exit 1
}
expected_execution_manifest_fingerprint="$release_manifest_deploy_fingerprint"

# 此版部署入口只接受同时理解迁移前/后 contract 且能收敛既有 V2 Run/Step 的三服务组合。
# Agent 探针还必须完整加载镜像内全部版本化 execution 资产，并与本次发布源码精确同指纹。
# 检查过程无网络、不挂载卷、不注入环境变量，不能靠 runtime=java 标签冒充 V2-aware。
sh "$durable_image_verifier" core "inkforge-core-api:$INKFORGE_IMAGE_TAG" >/dev/null
sh "$durable_image_verifier" agent "inkforge-agent-service:$INKFORGE_IMAGE_TAG" \
  "$expected_execution_manifest_fingerprint" >/dev/null

durable_rollout_config="$(python3 - .env <<'PY'
import sys
from pathlib import Path

allowed = {
    "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
    "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
    "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST",
    "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST",
    "V1_FRESH_AGENT_STARTS_ENABLED",
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
        print("durable-rollout-config:duplicate", file=sys.stderr)
        raise SystemExit(1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    values[key] = value
schema_ready = values.get("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "false").lower()
route_mode = values.get("DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off").lower()
v1_fresh_starts = values.get("V1_FRESH_AGENT_STARTS_ENABLED", "true").lower()
if schema_ready not in {"true", "false"} or route_mode not in {
    "off", "allowlist", "all"
} or v1_fresh_starts not in {"true", "false"}:
    print("durable-rollout-config:invalid", file=sys.stderr)
    raise SystemExit(1)
print(schema_ready)
print(route_mode)
print(values.get("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", "").strip())
print(values.get("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", "").strip())
print(v1_fresh_starts)
PY
)" || { echo "耐久 Agent 发布配置无法安全解析" >&2; exit 1; }
durable_schema_ready="$(printf '%s\n' "$durable_rollout_config" | sed -n '1p')"
durable_route_mode="$(printf '%s\n' "$durable_rollout_config" | sed -n '2p')"
durable_user_allowlist="$(printf '%s\n' "$durable_rollout_config" | sed -n '3p')"
durable_novel_allowlist="$(printf '%s\n' "$durable_rollout_config" | sed -n '4p')"
durable_v1_fresh_starts="$(printf '%s\n' "$durable_rollout_config" | sed -n '5p')"
expected_runtime_route="$deploy_runtime_route_mode"
[ "$durable_route_mode" = "$expected_runtime_route" ] || {
    echo "运行配置 route 与 release manifest 不一致" >&2
    exit 1
  }
[ "$durable_route_mode" != "all" ] || {
  echo "当前耐久 Agent 发布 Runbook 只授权 route-off 或交集 allowlist，禁止直接全量" >&2
  exit 1
}
[ "$durable_route_mode" != "allowlist" ] \
  || [ "$durable_v1_fresh_starts" = "true" ] || {
    echo "allowlist canary 必须保持 V1 fresh start 兼容入口开启" >&2
    exit 1
  }
release_canary_scope_sha256="$(read_release_manifest_field canary-scope-sha256)"
runtime_canary_scope_sha256="$(python3 - "$durable_user_allowlist" \
  "$durable_novel_allowlist" <<'PY'
import hashlib
import json
import re
import sys

pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
user_id, novel_id = sys.argv[1:]
if not pattern.fullmatch(user_id) or not pattern.fullmatch(novel_id):
    raise SystemExit("canary-scope-id")
payload = json.dumps(
    {"novelId": novel_id, "userId": user_id},
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode()
print(hashlib.sha256(payload).hexdigest())
PY
)" || {
  echo "耐久 Agent canary scope 不是精确单 userId 与单 novelId" >&2
  exit 1
}
[ "$runtime_canary_scope_sha256" = "$release_canary_scope_sha256" ] || {
  echo "运行配置 canary scope 与 release manifest 不一致" >&2
  exit 1
}

durable_migration_state="$(
  APP_DIR="$control_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$APP_DIR/.env" \
    sh "$durable_migration_helper" status novelwriter
)" || { echo "无法读取耐久 Agent 数据库状态" >&2; exit 1; }
case "$durable_migration_state" in
  unmigrated)
    [ "$durable_schema_ready" = "false" ] && [ "$durable_route_mode" = "off" ] || {
      echo "迁移前结构只允许 schemaReady=false、route=off" >&2
      exit 1
    }
    ;;
  migrated-empty-v2)
    if [ "$durable_schema_ready" = "false" ]; then
      [ "$durable_route_mode" = "off" ] || {
        echo "schemaReady=false 时耐久 Agent route 必须为 off" >&2
        exit 1
      }
    fi
    ;;
  migrated-with-v2)
    [ "$durable_schema_ready" = "true" ] || {
      echo "已有 V2 Run 后必须保持 schemaReady=true 以继续收敛" >&2
      exit 1
    }
    ;;
  partial)
    echo "耐久 Agent schema 处于 partial drift，停止部署" >&2
    exit 1
    ;;
  *) echo "耐久 Agent schema 状态无效" >&2; exit 1 ;;
esac

web_container="$(find_service_container web)"
core_container="$(find_service_container core-api)"
agent_container="$(find_service_container agent-service)"

existing_service_count="0"
[ -n "$web_container" ] && existing_service_count=$((existing_service_count + 1))
[ -n "$core_container" ] && existing_service_count=$((existing_service_count + 1))
[ -n "$agent_container" ] && existing_service_count=$((existing_service_count + 1))

previous_tag=""
previous_core_runtime=""
manifest_target_fingerprint="$(read_release_manifest_field target-manifest-fingerprint)"
manifest_rollback_fingerprint="$(read_release_manifest_field rollback-manifest-fingerprint)"
if [ "$manifest_target_fingerprint" = "$manifest_rollback_fingerprint" ]; then
  route_off_manifest_mismatch="0"
else
  route_off_manifest_mismatch="1"
fi
# 自动回滚的权威来源是切换前同一时刻实际运行的三容器，而不是可能经历过复用的历史标签。
if [ "$existing_service_count" -eq 0 ]; then
  echo "受保护发布缺少 manifest 冻结的当前三服务回滚组合" >&2
  exit 1
elif [ "$existing_service_count" -ne 3 ]; then
  echo "现有生产服务不完整，停止部署并等待人工检查" >&2
  exit 1
else
  verify_running_core_rollout_config "$core_container" \
    "$expected_runtime_route" "$release_canary_scope_sha256" any || exit 1
  current_web_digest="$(docker inspect --format '{{.Image}}' "$web_container")"
  current_core_digest="$(docker inspect --format '{{.Image}}' "$core_container")"
  current_agent_digest="$(docker inspect --format '{{.Image}}' "$agent_container")"
  [ "$current_web_digest" = "$release_manifest_start_web_digest" ] \
    && [ "$current_core_digest" = "$release_manifest_start_core_digest" ] \
    && [ "$current_agent_digest" = "$release_manifest_start_agent_digest" ] || {
      echo "当前运行三服务与 release manifest 冻结起点不一致" >&2
      exit 1
    }
  rollback_snapshot_tag="rollback-$durable_release_operation-$DEPLOY_SHA"
  web_image_id="$(
    snapshot_running_service_image \
      web inkforge-web "$web_container" "$rollback_snapshot_tag"
  )"
  core_image_id="$(
    snapshot_running_service_image \
      core-api inkforge-core-api "$core_container" "$rollback_snapshot_tag"
  )"
  agent_image_id="$(
    snapshot_running_service_image \
      agent-service inkforge-agent-service "$agent_container" "$rollback_snapshot_tag"
  )"

  if previous_core_runtime_label="$(core_image_runtime_label "$core_image_id")"; then
    previous_core_runtime="$(classify_core_runtime "$previous_core_runtime_label")"
  else
    echo "无法读取上一 Core 镜像 runtime 标签" >&2
    exit 1
  fi
  [ "$previous_core_runtime" != "unknown" ] || {
    echo "上一 Core 镜像 runtime 标签无法识别" >&2
    exit 1
  }
  if [ "$durable_migration_state" != "unmigrated" ]; then
    [ "$previous_core_runtime" = "java" ] || {
      echo "迁移后结构禁止把 V1-only Python Core 保留为自动回滚目标" >&2
      exit 1
    }
    sh "$durable_image_verifier" core "$core_image_id" >/dev/null || {
      echo "迁移后结构的上一 Core 镜像不是 V2-aware，停止部署" >&2
      exit 1
    }
    if [ "$durable_route_mode" = "allowlist" ]; then
      sh "$durable_image_verifier" agent "$agent_image_id" \
        "$expected_execution_manifest_fingerprint" >/dev/null || {
          echo "allowlist 的上一 Agent 回滚镜像与冻结 execution manifest 不兼容，停止部署" >&2
          exit 1
        }
    else
      if rollback_agent_probe="$(
        sh "$durable_image_verifier" agent "$agent_image_id"
      )"; then
        :
      else
        echo "迁移后结构的上一 Agent 镜像无法离线验证 execution manifest，停止部署" >&2
        exit 1
      fi
      case "$rollback_agent_probe" in
        v2-aware-image-ok:agent:*)
          rollback_agent_manifest_fingerprint="${rollback_agent_probe#v2-aware-image-ok:agent:}"
          ;;
        *)
          echo "迁移后结构的上一 Agent 镜像探针输出格式无效，停止部署" >&2
          exit 1
          ;;
      esac
      case "$rollback_agent_manifest_fingerprint" in
        ""|*[!0-9a-f]*)
          echo "迁移后结构的上一 Agent 镜像输出了无效 manifest 指纹，停止部署" >&2
          exit 1
          ;;
      esac
      [ "${#rollback_agent_manifest_fingerprint}" -eq 64 ] || {
        echo "迁移后结构的上一 Agent 镜像输出了无效 manifest 指纹，停止部署" >&2
        exit 1
      }
      if [ "$rollback_agent_manifest_fingerprint" != \
        "$expected_execution_manifest_fingerprint" ]; then
        route_off_manifest_mismatch="1"
      fi
    fi
    docker exec "$core_container" /usr/local/bin/inkforge-schema-guard >/dev/null || {
      echo "迁移后实时 PostgreSQL 未精确命中冻结 contract，停止部署" >&2
      exit 1
    }
  fi
  previous_tag="$rollback_snapshot_tag"
  echo "已冻结当前生产三服务精确回滚快照：${previous_tag}（${previous_core_runtime}）"
fi

if [ "$durable_route_mode" = "allowlist" ] && [ -z "$previous_tag" ]; then
  echo "allowlist canary 必须先冻结与当前 execution manifest 完全兼容的回滚镜像" >&2
  exit 1
fi

docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }
export INKFORGE_IMAGE_TAG
compose config >/dev/null
initialize_persistent_volumes

token_control="$release_lock_dir/token-usage-control"
mkdir "$token_control"
chmod 700 "$token_control"
mkdir "$token_control/scripts" "$token_control/scripts/migrations"
chmod 700 "$token_control/scripts" "$token_control/scripts/migrations"
cp "$control_dir/scripts/token-usage-production-migration.sh" "$token_control/scripts/"
cp "$control_dir/scripts/migrations/20260823_token_usage_details.production.sql" \
  "$control_dir/scripts/migrations/rollback_20260823_token_usage_details.sql" \
  "$token_control/scripts/migrations/"
cp "$APP_DIR/.env" "$token_control/.env"
chmod 600 "$token_control/.env" "$token_control/scripts/token-usage-production-migration.sh" \
  "$token_control/scripts/migrations/20260823_token_usage_details.production.sql" \
  "$token_control/scripts/migrations/rollback_20260823_token_usage_details.sql"
migration_helper="$control_dir/scripts/token-usage-production-migration.sh"
token_status=0
migration_state="$(APP_DIR="$token_control" sh "$migration_helper" status)" \
  || token_status=$?
rm -f -- "$token_control/.env" \
  "$token_control/scripts/token-usage-production-migration.sh" \
  "$token_control/scripts/migrations/20260823_token_usage_details.production.sql" \
  "$token_control/scripts/migrations/rollback_20260823_token_usage_details.sql"
rmdir "$token_control/scripts/migrations" "$token_control/scripts" "$token_control"
[ "$token_status" -eq 0 ] || {
  echo "无法读取生产 TokenUsage schema 状态" >&2
  exit "$token_status"
}
case "$migration_state" in
  migrated) ;;
  unmigrated) echo "受保护 Durable Agent 发布禁止夹带 TokenUsage DDL" >&2; exit 1 ;;
  partial)
    echo "生产 TokenUsage schema 处于部分迁移状态，停止部署" >&2
    exit 1
    ;;
  *) echo "生产 TokenUsage schema 状态无效" >&2; exit 1 ;;
esac

version_switch_started="0"

mark_release_transaction_failed() {
  printf 'failed\n' > "$release_lock_dir/.state.deploy-failed.partial"
  chmod 600 "$release_lock_dir/.state.deploy-failed.partial"
  mv -f "$release_lock_dir/.state.deploy-failed.partial" "$release_lock_dir/state"
}

rollback() {
  original_status="$1"
  trap - EXIT HUP INT TERM
  set +e
  if ! cleanup_deploy_bundle; then
    echo "部署源码 bundle 清理失败" >&2
  fi
  echo "新版本部署失败（退出码：${original_status}）" >&2

  if [ "$version_switch_started" != "1" ]; then
    echo "失败发生在镜像切换前，现有生产容器保持运行" >&2
    if ! mark_release_transaction_failed; then
      echo "发布失败且无法把 release transaction 标记为 failed；锁目录仍保留" >&2
    fi
    exit "$original_status"
  fi

  if [ -z "$previous_tag" ]; then
    echo "本次为首次部署，没有可自动恢复的上一版本" >&2
    if ! mark_release_transaction_failed; then
      echo "发布失败且无法把 release transaction 标记为 failed；锁目录仍保留" >&2
    fi
    exit "$original_status"
  fi

  INKFORGE_IMAGE_TAG="$previous_tag"
  export INKFORGE_IMAGE_TAG
  if [ "$previous_core_runtime" = "python" ]; then
    compose_python_rollback up --no-build -d --wait
  else
    compose up --no-build -d --wait
  fi
  rollback_status="$?"
  if [ "$rollback_status" -eq 0 ]; then
    refresh_nginx
    rollback_status="$?"
  fi
  if [ "$rollback_status" -eq 0 ]; then
    if [ "$previous_core_runtime" = "python" ]; then
      verify_python_rollback_stack
    else
      verify_java_stack
    fi
    rollback_status="$?"
  fi

  if [ "$rollback_status" -eq 0 ]; then
    DURABLE_AGENT_BOUNDARY_OUTCOME=compensated \
      sh "$durable_release_driver" mark-live-boundary-applied \
        "compose-$durable_release_operation" >/dev/null
    rollback_status="$?"
  fi
  if ! mark_release_transaction_failed; then
    echo "发布失败且无法把 release transaction 标记为 failed；锁目录仍保留" >&2
  fi
  if [ "$rollback_status" -eq 0 ]; then
    echo "新版本部署失败，旧版本已恢复"
  else
    echo "新版本部署失败，自动回滚也失败（退出码：${rollback_status}）" >&2
  fi
  exit "$original_status"
}

trap 'rollback "$?"' EXIT

# 到此所有结构只读门禁已通过。live drain、一次性 claim、git reset 与 Compose
# 位于同一 trusted driver 进程；claim 后任何崩溃都视为 outcome-unknown，禁止重放。
sh "$durable_release_driver" consume-live-boundary \
  "compose-$durable_release_operation" >/dev/null
safe_git reset --hard "$DEPLOY_SHA"
version_switch_started="1"
compose up --no-build -d --wait
refresh_nginx
verify_java_stack
new_core_container="$(find_service_container core-api)"
[ -n "$new_core_container" ] \
  && verify_running_core_rollout_config "$new_core_container" \
    "$expected_runtime_route" "$release_canary_scope_sha256" \
      "$durable_v1_fresh_starts" || {
      echo "部署后运行 Core 的 route/canary scope 复验失败" >&2
      exit 1
    }
cleanup_deploy_bundle
sh "$durable_release_driver" mark-live-boundary-applied \
  "compose-$durable_release_operation" >/dev/null
trap - EXIT HUP INT TERM
echo "生产编排已启动"
