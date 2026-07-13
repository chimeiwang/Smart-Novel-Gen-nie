#!/usr/bin/env bash
set -euo pipefail

: "${SERVER_HOST:?必须设置服务器地址}"
: "${SERVER_USER:?必须设置服务器用户}"
: "${SSH_KEY_PATH:?必须设置 SSH 私钥路径}"
: "${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
: "${DEPLOY_SHA:?必须设置部署提交}"

ssh_options=(
  -o StrictHostKeyChecking=no
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=20
  -o TCPKeepAlive=yes
  -i "$SSH_KEY_PATH"
)
remote="${SERVER_USER}@${SERVER_HOST}"
images=(
  "inkforge-web:${INKFORGE_IMAGE_TAG}"
  "inkforge-core-api:${INKFORGE_IMAGE_TAG}"
  "inkforge-agent-service:${INKFORGE_IMAGE_TAG}"
)
services=(web core-api agent-service)
images_to_upload=()

remote_ssh() {
  ssh "${ssh_options[@]}" "$remote" "$@"
}

server_has_image() {
  local image_id="$1"
  printf '%s\n' "$image_id" |
    remote_ssh 'read -r image_id; docker image inspect "$image_id" >/dev/null 2>&1'
}

server_tag_image() {
  local image_id="$1"
  local image="$2"
  printf '%s\n%s\n' "$image_id" "$image" |
    remote_ssh 'read -r image_id; read -r image; docker image tag "$image_id" "$image"'
}

server_current_image() {
  local service="$1"
  echo "读取服务器当前运行镜像：$service" >&2
  printf '%s\n' "$service" | remote_ssh '
    read -r service
    container_id="$(docker ps -q \
      --filter label=com.docker.compose.project=inkforge \
      --filter "label=com.docker.compose.service=$service" | head -n 1)"
    [ -n "$container_id" ] || exit 1
    docker inspect --format "{{.Config.Image}}" "$container_id"
  '
}

server_tag_image_ref() {
  local source_image="$1"
  local target_image="$2"
  printf '%s\n%s\n' "$source_image" "$target_image" |
    remote_ssh 'read -r source_image; read -r target_image; docker image tag "$source_image" "$target_image"'
}

build_inputs_unchanged() {
  local service="$1"
  local base_sha="$2"
  local paths=()

  case "$service" in
    web)
      paths=(
        package.json
        package-lock.json
        apps/web
        packages/api-client
        infra/docker/web.Dockerfile
      )
      ;;
    core-api)
      paths=(
        pyproject.toml
        uv.lock
        .python-version
        packages/service-auth
        packages/service-contracts
        apps/core-api
        infra/docker/core-api.Dockerfile
      )
      ;;
    agent-service)
      paths=(
        pyproject.toml
        uv.lock
        .python-version
        packages/service-auth
        packages/service-contracts
        apps/agent-service
        infra/docker/agent-service.Dockerfile
      )
      ;;
    *)
      return 1
      ;;
  esac

  git cat-file -e "${base_sha}^{commit}" 2>/dev/null || return 1
  git diff --quiet "$base_sha" "$DEPLOY_SHA" -- "${paths[@]}"
}

reuse_deployed_image() {
  local service="$1"
  local target_image="$2"
  local current_image
  local base_sha

  current_image="$(server_current_image "$service")" || return 1
  base_sha="${current_image##*:}"
  [[ "$base_sha" =~ ^[0-9a-f]{40}$ ]] || return 1
  build_inputs_unchanged "$service" "$base_sha" || return 1
  server_tag_image_ref "$current_image" "$target_image"
  echo "复用构建输入未变化的服务器镜像：$target_image"
}

for index in "${!images[@]}"; do
  image="${images[$index]}"
  service="${services[$index]}"
  if reuse_deployed_image "$service" "$image"; then
    continue
  fi
  image_id="$(docker image inspect --format='{{.Id}}' "$image")"
  if server_has_image "$image_id"; then
    server_tag_image "$image_id" "$image"
    echo "复用服务器已有镜像内容：$image"
  else
    images_to_upload+=("$image")
  fi
done

if [ "${#images_to_upload[@]}" -eq 0 ]; then
  echo "三张镜像内容均已存在，跳过镜像传输"
  exit 0
fi

echo "需要上传 ${#images_to_upload[@]} 张新镜像"
docker save "${images_to_upload[@]}" | gzip -9 | remote_ssh 'gunzip | docker load'
