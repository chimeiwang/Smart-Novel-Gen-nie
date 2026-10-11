#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"
REPO_URL="${REPO_URL:-https://github.com/chimeiwang/Smart-Novel-Gen-nie.git}"
BRANCH="${BRANCH:-main}"
DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"
DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:-}"
INKFORGE_IMAGE_TAG="${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
compose_file="infra/compose.yaml"
durable_migration_helper="scripts/durable-agent-execution-migration.sh"
image_verifier="scripts/verify-retired-engine-image.sh"
rollback_compose_file="$APP_DIR/infra/.rollback-${DEPLOY_SHA}.yaml"

# Compose 的调用进程环境优先于 --env-file。部署配置必须只来自服务器已审核的
# .env，不能被 SSH AcceptEnv、操作者 shell 或旧自动化残留覆盖。
unset DATABASE_URL EXECUTION_REDIS_URL HISTORICAL_WORKFLOW_SCHEMA_READY \
  DURABLE_AGENT_EXECUTION_SCHEMA_READY \
  DURABLE_AGENT_EXECUTION_ROUTE_MODE \
  DURABLE_AGENT_EXECUTION_USER_ALLOWLIST \
  DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST \
  V1_FRESH_AGENT_STARTS_ENABLED

cleanup_deploy_bundle() {
  [ -z "$DEPLOY_BUNDLE_PATH" ] || rm -f -- "$DEPLOY_BUNDLE_PATH"
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
  [ -f "$DEPLOY_BUNDLE_PATH" ] && [ -r "$DEPLOY_BUNDLE_PATH" ] || {
    echo "部署源码 bundle 不存在或不可读" >&2
    exit 1
  }
fi

# Core 运行时必须来自镜像标签；现有 V2 数据只允许兼容的 Java 镜像组合。
compose() {
  docker compose --env-file .env -f "$compose_file" "$@"
}

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
}

refresh_nginx() {
  compose up --no-build -d --wait --no-deps --force-recreate nginx
}

find_service_container() {
  service="$1"
  docker ps --no-trunc -q \
    --filter "label=com.docker.compose.project=inkforge" \
    --filter "label=com.docker.compose.service=$service" \
    | head -n 1
}

safe_git() {
  git -c safe.directory="$APP_DIR" "$@"
}

verify_java_stack() {
  compose ps &&
  sh scripts/verify-running-core-schema.sh "$(compose ps -q core-api)" &&
  COMPOSE_ENV_FILE=.env COMPOSE_OVERRIDE_FILE= sh scripts/compose_smoke.sh
}

core_image_runtime_label() {
  docker image inspect \
    --format '{{ index .Config.Labels "cn.inkforge.core.runtime" }}' "$1"
}

classify_core_runtime() {
  case "$1" in
    java) printf '%s\n' java ;;
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
command -v flock >/dev/null 2>&1 || { echo "缺少 flock 命令" >&2; exit 1; }

# APP_DIR 是服务器专用部署检出目录；DEPLOY_SHA 将实际代码固定到 CI 已构建镜像对应的提交。
mkdir -p "$APP_DIR"
[ -d "$APP_DIR" ] && [ ! -L "$APP_DIR" ] || {
  echo "服务器 APP_DIR 必须是非符号链接目录" >&2
  exit 1
}
deployment_lock_file="$APP_DIR/.inkforge-production.lock"
if [ -e "$deployment_lock_file" ] || [ -L "$deployment_lock_file" ]; then
  [ -f "$deployment_lock_file" ] && [ ! -L "$deployment_lock_file" ] || {
    echo "生产部署锁文件无效" >&2
    exit 1
  }
fi
exec 9>>"$deployment_lock_file"
chmod 600 "$deployment_lock_file"
flock -n 9 || {
  echo "已有其他生产部署或迁移在运行" >&2
  exit 1
}
# 只有取得服务器部署锁的进程才拥有并清理本次 bundle；同一提交的并发调用
# 不能在锁拒绝路径删除正在被持锁进程读取的文件。
if [ -n "$DEPLOY_BUNDLE_PATH" ]; then
  trap cleanup_deploy_bundle EXIT
fi
cd "$APP_DIR"

if [ ! -d .git ]; then
  safe_git init -b "$BRANCH"
  safe_git remote add origin "$REPO_URL"
else
  safe_git remote set-url origin "$REPO_URL"
fi

# 首次跨引擎发布必须连同旧服务依赖一起保留；回滚不能拿新 Compose 启动旧 Agent。
if [ -f "$compose_file" ] && [ ! -e "$rollback_compose_file" ]; then
  APP_DIR="$APP_DIR" DEPLOY_SHA="$DEPLOY_SHA" python3 - <<'PY_SNAPSHOT'
from pathlib import Path
import os
import shutil
app = Path(os.environ["APP_DIR"])
sha = os.environ["DEPLOY_SHA"]
state = app / "infra" / (".rollback-" + sha + "-config")
state.mkdir(mode=0o700, exist_ok=True)
os.chmod(state, 0o700)
source = (app / "infra/compose.yaml").read_text()
for name in ("redis", "nginx"):
    original = app / "infra" / name
    if original.exists():
        destination = state / name
        shutil.copytree(original, destination, dirs_exist_ok=True)
        source = source.replace("./" + name + "/", str(destination) + "/")
target = app / "infra" / (".rollback-" + sha + ".yaml")
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(source)
PY_SNAPSHOT
fi

if [ -n "$DEPLOY_BUNDLE_PATH" ]; then
  # 标准 CI 部署只信任 runner 已 checkout 并经固定主机身份上传的 bundle；服务器无需访问 GitHub。
  safe_git bundle verify "$DEPLOY_BUNDLE_PATH"
  safe_git fetch "$DEPLOY_BUNDLE_PATH" HEAD
  bundle_sha="$(safe_git rev-parse FETCH_HEAD)"
  [ "$bundle_sha" = "$DEPLOY_SHA" ] || {
    echo "部署源码 bundle 与部署提交不一致" >&2
    exit 1
  }
  safe_git update-ref "refs/remotes/origin/$BRANCH" "$DEPLOY_SHA"
else
  # 无 bundle 只保留给人工兼容流程；GitHub Actions 标准路径必须始终提供 bundle。
  max_fetch_attempts="3"
  fetch_attempt="1"
  while ! safe_git -c http.version=HTTP/1.1 fetch --depth=1 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  do
    if [ "$fetch_attempt" -lt "$max_fetch_attempts" ]; then
      next_attempt=$((fetch_attempt + 1))
      echo "Git 获取失败，等待后进行第 $next_attempt/$max_fetch_attempts 次尝试" >&2
      sleep $((fetch_attempt * 3))
      fetch_attempt="$next_attempt"
    else
      echo "Git 获取连续失败 $max_fetch_attempts 次，停止部署" >&2
      exit 1
    fi
  done
fi
remote_sha="$(safe_git rev-parse "refs/remotes/origin/$BRANCH")"
[ "$remote_sha" = "$DEPLOY_SHA" ] || {
  echo "远程分支提交与部署提交不一致" >&2
  exit 1
}
safe_git reset --hard "$DEPLOY_SHA"

[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
[ -r .env ] || { echo "部署用户无法读取 .env" >&2; exit 1; }
[ -r "$durable_migration_helper" ] || { echo "缺少耐久 Agent 具名迁移 helper" >&2; exit 1; }
[ -r "$image_verifier" ] || { echo "缺少引擎退役镜像检查器" >&2; exit 1; }
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

# 离线证明新镜像已移除执行器，同时仍可读取历史来源与结构契约。
sh "$image_verifier" core "inkforge-core-api:$INKFORGE_IMAGE_TAG" >/dev/null
sh "$image_verifier" agent "inkforge-agent-service:$INKFORGE_IMAGE_TAG" >/dev/null

durable_migration_state="$(
  APP_DIR="$APP_DIR" DURABLE_AGENT_MIGRATION_ENV_FILE="$APP_DIR/.env" \
    sh "$durable_migration_helper" status novelwriter
)" || { echo "无法读取历史结构状态" >&2; exit 1; }
case "$durable_migration_state" in
  unmigrated|migrated-empty-v2|migrated-with-v2) ;;
  *) echo "历史结构存在漂移，停止部署" >&2; exit 1 ;;
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
# 自动回滚的权威来源是切换前同一时刻实际运行的三容器，而不是可能经历过复用的历史标签。
if [ "$existing_service_count" -eq 0 ]; then
  [ "$durable_migration_state" = unmigrated ] || {
    echo "已有历史执行结构但现网 Core 缺失，无法证明日志已排空，停止首次部署" >&2
    exit 1
  }
  echo "未发现现有生产容器，本次按首次部署处理"
elif [ "$existing_service_count" -ne 3 ]; then
  echo "现有生产服务不完整，停止部署并等待人工检查" >&2
  exit 1
else
  rollback_snapshot_tag="rollback-$DEPLOY_SHA"
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
  [ -r "$rollback_compose_file" ] || { echo "缺少旧编排恢复点" >&2; exit 1; }
  sh scripts/verify-running-core-schema.sh "$core_container" >/dev/null || {
    echo "实时 PostgreSQL 未精确命中冻结 contract，停止部署" >&2
    exit 1
  }
  previous_tag="$rollback_snapshot_tag"
  echo "已冻结当前生产三服务精确回滚快照：${previous_tag}（${previous_core_runtime}）"
fi

docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }
export INKFORGE_IMAGE_TAG
compose config >/dev/null
initialize_persistent_volumes

migration_helper="$APP_DIR/scripts/token-usage-production-migration.sh"
[ -r "$migration_helper" ] || { echo "缺少固定生产数据库迁移 helper" >&2; exit 1; }
# 部署只获准调用这一个具名迁移 helper；partial 状态不能自动推断修复方向。
migration_state="$(sh "$migration_helper" status)" || {
  echo "无法读取生产 TokenUsage schema 状态" >&2
  exit 1
}
case "$migration_state" in
  migrated) ;;
  unmigrated)
    echo "普通部署不执行 TokenUsage DDL，请使用具名迁移流程" >&2
    exit 1
    ;;
  partial)
    echo "生产 TokenUsage schema 处于部分迁移状态，停止部署" >&2
    exit 1
    ;;
  *) echo "生产 TokenUsage schema 状态无效" >&2; exit 1 ;;
esac

version_switch_started="0"

rollback() {
  original_status="$1"
  trap - EXIT
  set +e
  if ! cleanup_deploy_bundle; then
    echo "部署源码 bundle 清理失败" >&2
  fi
  echo "新版本部署失败（退出码：${original_status}）" >&2

  if [ "$version_switch_started" != "1" ]; then
    echo "失败发生在镜像切换前，现有生产容器保持运行" >&2
    exit "$original_status"
  fi

  if [ -z "$previous_tag" ]; then
    echo "本次为首次部署，没有可自动恢复的上一版本" >&2
    exit "$original_status"
  fi

  compose_file="$rollback_compose_file"
  INKFORGE_IMAGE_TAG="$previous_tag"
  export INKFORGE_IMAGE_TAG
  compose up --no-build -d --wait
  rollback_status="$?"
  if [ "$rollback_status" -eq 0 ]; then
    refresh_nginx
    rollback_status="$?"
  fi
  if [ "$rollback_status" -eq 0 ]; then
    verify_java_stack
    rollback_status="$?"
  fi

  if [ "$rollback_status" -eq 0 ]; then
    echo "新版本部署失败，旧版本已恢复"
  else
    echo "新版本部署失败，自动回滚也失败（退出码：${rollback_status}）" >&2
  fi
  exit "$original_status"
}

trap 'rollback "$?"' EXIT

# 在新建路由已关闭的现网做只读排空检查，并保存可恢复数据库与旧日志快照。
# 失败发生在切换前；不会为通过检查删除任务或把未知用量改成零。
if [ -n "$core_container" ]; then
  execution_container="$(find_service_container execution-redis)"
  APP_DIR="$APP_DIR" DEPLOY_SHA="$DEPLOY_SHA" \
    python3 scripts/engine_retirement_preflight.py "$core_container" "$execution_container"
fi

# 到此数据库已达到目标状态且幂等复验通过，才允许承担切换生产容器的回滚责任。
version_switch_started="1"
compose up --no-build -d --wait
refresh_nginx
verify_java_stack
# 保留旧日志卷及容器作为恢复点，只在新栈验证成功后停止退役日志服务。
if [ -n "${execution_container:-}" ]; then
  docker stop "$execution_container" >/dev/null
fi
cleanup_deploy_bundle
trap - EXIT
echo "生产编排已启动"
