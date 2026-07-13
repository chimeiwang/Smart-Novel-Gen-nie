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

git -c http.version=HTTP/1.1 fetch --depth=1 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
remote_sha="$(git rev-parse "refs/remotes/origin/$BRANCH")"
[ "$remote_sha" = "$DEPLOY_SHA" ] || {
  echo "远程分支提交与部署提交不一致" >&2
  exit 1
}
git reset --hard "$DEPLOY_SHA"

[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
for key_file in \
  core-to-agent-private.pem \
  core-to-agent-jwks.json \
  agent-to-core-private.pem \
  agent-to-core-jwks.json
do
  [ -f "infra/secrets/$key_file" ] || { echo "缺少服务密钥：$key_file" >&2; exit 1; }
done

for image in \
  "inkforge-web:$INKFORGE_IMAGE_TAG" \
  "inkforge-core-api:$INKFORGE_IMAGE_TAG" \
  "inkforge-agent-service:$INKFORGE_IMAGE_TAG"
do
  docker image inspect "$image" >/dev/null 2>&1 || { echo "缺少预构建镜像：$image" >&2; exit 1; }
done

docker compose --env-file .env -f "$compose_file" config >/dev/null
export INKFORGE_IMAGE_TAG
docker compose --env-file .env -f "$compose_file" up --no-build -d --wait
docker compose --env-file .env -f "$compose_file" ps
echo "生产编排已启动"
