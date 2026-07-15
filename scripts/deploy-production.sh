#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"
REPO_URL="${REPO_URL:-https://github.com/chimeiwang/Smart-Novel-Gen-nie.git}"
BRANCH="${BRANCH:-main}"
DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"
INKFORGE_IMAGE_TAG="${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
compose_file="infra/compose.yaml"

compose() {
  docker compose --env-file .env -f "$compose_file" "$@"
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

safe_git() {
  git -c safe.directory="$APP_DIR" "$@"
}

verify_stack() {
  compose ps &&
  compose exec -T core-api python -c \
    'import asyncio, os; from inkforge_core.db.schema_guard import verify_live_schema; from inkforge_core.db.session import SCHEMA_CONTRACT_PATH; result = asyncio.run(verify_live_schema(os.environ["DATABASE_URL"], SCHEMA_CONTRACT_PATH)); print(result.fingerprint); raise SystemExit(0 if result.ready else 1)' &&
  COMPOSE_ENV_FILE=.env COMPOSE_OVERRIDE_FILE= sh scripts/compose_smoke.sh
}

command -v docker >/dev/null 2>&1 || { echo "缺少 docker 命令" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "缺少 git 命令" >&2; exit 1; }

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  safe_git init -b "$BRANCH"
  safe_git remote add origin "$REPO_URL"
else
  safe_git remote set-url origin "$REPO_URL"
fi

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
remote_sha="$(safe_git rev-parse "refs/remotes/origin/$BRANCH")"
[ "$remote_sha" = "$DEPLOY_SHA" ] || {
  echo "远程分支提交与部署提交不一致" >&2
  exit 1
}
safe_git reset --hard "$DEPLOY_SHA"

[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
[ -r .env ] || { echo "部署用户无法读取 .env" >&2; exit 1; }
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

web_container="$(find_service_container web)"
core_container="$(find_service_container core-api)"
agent_container="$(find_service_container agent-service)"

existing_service_count="0"
[ -n "$web_container" ] && existing_service_count=$((existing_service_count + 1))
[ -n "$core_container" ] && existing_service_count=$((existing_service_count + 1))
[ -n "$agent_container" ] && existing_service_count=$((existing_service_count + 1))

previous_tag=""
if [ "$existing_service_count" -eq 0 ]; then
  echo "未发现现有生产容器，本次按首次部署处理"
elif [ "$existing_service_count" -ne 3 ]; then
  echo "现有生产服务不完整，停止部署并等待人工检查" >&2
  exit 1
else
  web_image="$(docker inspect --format '{{.Config.Image}}' "$web_container")"
  core_image="$(docker inspect --format '{{.Config.Image}}' "$core_container")"
  agent_image="$(docker inspect --format '{{.Config.Image}}' "$agent_container")"

  case "$web_image" in
    inkforge-web:*) web_tag="${web_image#inkforge-web:}" ;;
    *) echo "web 容器镜像仓库不符合生产约定" >&2; exit 1 ;;
  esac
  case "$core_image" in
    inkforge-core-api:*) core_tag="${core_image#inkforge-core-api:}" ;;
    *) echo "core-api 容器镜像仓库不符合生产约定" >&2; exit 1 ;;
  esac
  case "$agent_image" in
    inkforge-agent-service:*) agent_tag="${agent_image#inkforge-agent-service:}" ;;
    *) echo "agent-service 容器镜像仓库不符合生产约定" >&2; exit 1 ;;
  esac

  [ -n "$web_tag" ] && [ "$web_tag" = "$core_tag" ] && [ "$web_tag" = "$agent_tag" ] || {
    echo "现有生产服务镜像标签不一致，停止部署并等待人工检查" >&2
    exit 1
  }
  for image in "$web_image" "$core_image" "$agent_image"
  do
    docker image inspect "$image" >/dev/null 2>&1 || {
      echo "现有生产镜像已缺失，无法保证自动回滚：$image" >&2
      exit 1
    }
  done
  previous_tag="$web_tag"
  echo "已确认可回滚的上一生产镜像标签：$previous_tag"
fi

docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }
export INKFORGE_IMAGE_TAG
compose config >/dev/null

rollback() {
  original_status="$1"
  trap - EXIT
  set +e
  echo "新版本部署失败（退出码：$original_status）" >&2

  if [ -z "$previous_tag" ]; then
    echo "本次为首次部署，没有可自动恢复的上一版本" >&2
    exit "$original_status"
  fi

  INKFORGE_IMAGE_TAG="$previous_tag"
  export INKFORGE_IMAGE_TAG
  compose up --no-build -d --wait
  rollback_status="$?"
  if [ "$rollback_status" -eq 0 ]; then
    refresh_nginx
    rollback_status="$?"
  fi
  if [ "$rollback_status" -eq 0 ]; then
    verify_stack
    rollback_status="$?"
  fi

  if [ "$rollback_status" -eq 0 ]; then
    echo "新版本部署失败，旧版本已恢复"
  else
    echo "新版本部署失败，自动回滚也失败（退出码：$rollback_status）" >&2
  fi
  exit "$original_status"
}

trap 'rollback "$?"' EXIT
compose up --no-build -d --wait
refresh_nginx
verify_stack
trap - EXIT
echo "生产编排已启动"
