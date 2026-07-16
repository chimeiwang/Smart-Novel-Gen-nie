#!/usr/bin/env bash
set -euo pipefail

: "${SERVER_HOST:?必须设置服务器地址}"
: "${SERVER_USER:?必须设置服务器用户}"
: "${SSH_KEY_PATH:?必须设置 SSH 私钥路径}"
: "${SSH_KNOWN_HOSTS_FILE:?必须设置 known_hosts 文件路径}"
: "${INKFORGE_IMAGE_TAG:?必须设置镜像标签}"
: "${DEPLOY_SHA:?必须设置部署提交}"

CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-15}"
REMOTE_COMMAND_TIMEOUT_SECONDS="${REMOTE_COMMAND_TIMEOUT_SECONDS:-300}"
IMAGE_ARCHIVE_TIMEOUT_SECONDS="${IMAGE_ARCHIVE_TIMEOUT_SECONDS:-600}"
IMAGE_UPLOAD_TIMEOUT_SECONDS="${IMAGE_UPLOAD_TIMEOUT_SECONDS:-1200}"
REMOTE_DOCKER_SAFETY_BYTES="${REMOTE_DOCKER_SAFETY_BYTES:-536870912}"

validate_timeout() {
  local name="$1"
  local value="$2"
  local maximum="$3"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]] || [ "$value" -gt "$maximum" ]; then
    echo "$name 必须是 1 到 $maximum 之间的整数，当前值：$value" >&2
    exit 1
  fi
}

validate_timeout CONNECT_TIMEOUT_SECONDS "$CONNECT_TIMEOUT_SECONDS" 120
validate_timeout REMOTE_COMMAND_TIMEOUT_SECONDS "$REMOTE_COMMAND_TIMEOUT_SECONDS" 900
validate_timeout IMAGE_ARCHIVE_TIMEOUT_SECONDS "$IMAGE_ARCHIVE_TIMEOUT_SECONDS" 1800
validate_timeout IMAGE_UPLOAD_TIMEOUT_SECONDS "$IMAGE_UPLOAD_TIMEOUT_SECONDS" 3600
validate_timeout REMOTE_DOCKER_SAFETY_BYTES "$REMOTE_DOCKER_SAFETY_BYTES" 10737418240

[ -r "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件不可读：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}
[ -s "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件为空：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}

ssh_options=(
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE"
  -o "ConnectTimeout=$CONNECT_TIMEOUT_SECONDS"
  -o ConnectionAttempts=2
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
  timeout --kill-after=30s "$REMOTE_COMMAND_TIMEOUT_SECONDS" \
    ssh "${ssh_options[@]}" "$remote" "$@"
}

preflight_remote() {
  echo "开始检查服务器 Docker 与文件系统容量"
  remote_ssh '
    set -eu
    command -v bash >/dev/null
    docker_root="$(docker info --format "{{.DockerRootDir}}")"
    [ -n "$docker_root" ]
    echo "服务器 Docker 响应正常，数据目录：$docker_root"
    echo "Docker 数据目录与临时目录容量："
    df -Pk "$docker_root" /tmp
  '
  echo "服务器预检完成"
}

server_has_image() {
  local image_id="$1"
  printf '%s\n' "$image_id" |
    remote_ssh '
      read -r image_id
      if docker image inspect "$image_id" >/dev/null 2>&1; then
        exit 0
      fi
      if docker info >/dev/null 2>&1; then
        exit 20
      fi
      exit 21
    '
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
    container_ids="$(docker ps -q \
      --filter label=com.docker.compose.project=inkforge \
      --filter "label=com.docker.compose.service=$service")" || exit 21
    set -- $container_ids
    container_id="${1:-}"
    [ -n "$container_id" ] || exit 20
    docker inspect --format "{{.Config.Image}}" "$container_id"
  '
}

server_require_capacity() {
  local image="$1"
  local image_size="$2"
  local required_bytes=$((image_size * 2 + REMOTE_DOCKER_SAFETY_BYTES))

  printf '%s\n%s\n' "$image" "$required_bytes" | remote_ssh '
    set -eu
    read -r image
    read -r required_bytes
    docker_root="$(docker info --format "{{.DockerRootDir}}")"
    available_kb="$(df -Pk "$docker_root" | awk "NR == 2 { print \$4 }")"
    available_bytes=$((available_kb * 1024))
    if [ "$available_bytes" -lt "$required_bytes" ]; then
      echo "服务器 Docker 容量不足：$image，需要至少 ${required_bytes} 字节，当前可用 ${available_bytes} 字节" >&2
      exit 22
    fi
    echo "服务器 Docker 容量满足要求：$image，需要 ${required_bytes} 字节，当前可用 ${available_bytes} 字节"
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
  local current_status
  local base_sha

  if current_image="$(server_current_image "$service")"; then
    :
  else
    current_status=$?
    if [ "$current_status" -eq 20 ]; then
      return 1
    fi
    echo "服务器镜像查询失败：$service，退出码 $current_status" >&2
    return 2
  fi
  base_sha="${current_image##*:}"
  [[ "$base_sha" =~ ^[0-9a-f]{40}$ ]] || return 1
  build_inputs_unchanged "$service" "$base_sha" || return 1
  if ! server_tag_image_ref "$current_image" "$target_image"; then
    echo "服务器镜像复用打标失败：$service" >&2
    return 2
  fi
  echo "复用构建输入未变化的服务器镜像：$target_image"
}

preflight_remote

for index in "${!images[@]}"; do
  image="${images[$index]}"
  service="${services[$index]}"
  if reuse_deployed_image "$service" "$image"; then
    continue
  else
    reuse_status=$?
    if [ "$reuse_status" -eq 2 ]; then
      exit 1
    fi
  fi
  image_id="$(docker image inspect --format='{{.Id}}' "$image")"
  if server_has_image "$image_id"; then
    server_tag_image "$image_id" "$image"
    echo "复用服务器已有镜像内容：$image"
  else
    image_query_status=$?
    if [ "$image_query_status" -eq 20 ]; then
      images_to_upload+=("$image")
    else
      echo "服务器镜像内容查询失败：$service，退出码 $image_query_status" >&2
      exit 1
    fi
  fi
done

if [ "${#images_to_upload[@]}" -eq 0 ]; then
  echo "三张镜像内容均已存在，跳过镜像传输"
  exit 0
fi

echo "需要上传 ${#images_to_upload[@]} 张新镜像"

upload_temp_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/inkforge-images.XXXXXX")"
cleanup_upload_archives() {
  if [ -n "${upload_temp_dir:-}" ] && [ -d "$upload_temp_dir" ]; then
    rm -rf -- "$upload_temp_dir"
  fi
}
trap cleanup_upload_archives EXIT

for index in "${!images_to_upload[@]}"; do
  image="${images_to_upload[$index]}"
  archive="$upload_temp_dir/image-$index.tar.gz"

  archive_started=$SECONDS
  echo "开始归档镜像：$image"
  if timeout --kill-after=30s "$IMAGE_ARCHIVE_TIMEOUT_SECONDS" \
    bash -o pipefail -c 'docker save "$1" | gzip -1 > "$2"' \
    upload-archive "$image" "$archive"; then
    :
  else
    archive_status=$?
    if [ "$archive_status" -eq 124 ]; then
      echo "镜像归档超时：$image，限制 ${IMAGE_ARCHIVE_TIMEOUT_SECONDS} 秒" >&2
    else
      echo "镜像归档失败：$image，退出码 $archive_status" >&2
    fi
    exit "$archive_status"
  fi
  archive_size="$(stat -c %s "$archive")"
  echo "镜像归档完成：$image，压缩后 ${archive_size} 字节，耗时 $((SECONDS - archive_started)) 秒"

  image_size="$(docker image inspect --format='{{.Size}}' "$image")"
  server_require_capacity "$image" "$image_size"

  upload_started=$SECONDS
  echo "开始传输并导入镜像：$image，超时 ${IMAGE_UPLOAD_TIMEOUT_SECONDS} 秒"
  if timeout --kill-after=30s "$IMAGE_UPLOAD_TIMEOUT_SECONDS" \
    ssh "${ssh_options[@]}" "$remote" \
    "bash -o pipefail -c 'gunzip | docker load'" < "$archive"; then
    echo "镜像传输并导入完成：$image，耗时 $((SECONDS - upload_started)) 秒"
  else
    upload_status=$?
    if [ "$upload_status" -eq 124 ]; then
      echo "镜像传输或导入超时：$image，限制 ${IMAGE_UPLOAD_TIMEOUT_SECONDS} 秒" >&2
    else
      echo "镜像传输或导入失败：$image，退出码 $upload_status" >&2
    fi
    exit "$upload_status"
  fi

  rm -f -- "$archive"
done
