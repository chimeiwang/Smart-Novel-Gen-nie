#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/srv/smart-novel-gen}"
REPO_URL="${REPO_URL:-https://github.com/chimeiwang/Smart-Novel-Gen-nie.git}"
BRANCH="${BRANCH:-main}"
DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"
INKFORGE_IMAGE_TAG="${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
compose_file="infra/compose.yaml"

command -v docker >/dev/null 2>&1 || { echo "缺少 docker 命令" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "缺少 git 命令" >&2; exit 1; }

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  git init -b "$BRANCH"
  git remote add origin "$REPO_URL"
else
  git remote set-url origin "$REPO_URL"
fi

max_fetch_attempts="3"
fetch_attempt="1"
while ! git -c http.version=HTTP/1.1 fetch --depth=1 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
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
remote_sha="$(git rev-parse "refs/remotes/origin/$BRANCH")"
[ "$remote_sha" = "$DEPLOY_SHA" ] || {
  echo "远程分支提交与部署提交不一致" >&2
  exit 1
}
git reset --hard "$DEPLOY_SHA"

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

export INKFORGE_IMAGE_TAG
docker compose --env-file .env -f "$compose_file" config >/dev/null
docker compose --env-file .env -f "$compose_file" up --no-build -d --wait
docker compose --env-file .env -f "$compose_file" ps
echo "生产编排已启动"
