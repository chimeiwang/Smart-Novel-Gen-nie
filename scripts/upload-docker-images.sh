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
IMAGE_LOAD_TIMEOUT_SECONDS="${IMAGE_LOAD_TIMEOUT_SECONDS:-600}"
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
validate_timeout IMAGE_LOAD_TIMEOUT_SECONDS "$IMAGE_LOAD_TIMEOUT_SECONDS" 1800
validate_timeout REMOTE_DOCKER_SAFETY_BYTES "$REMOTE_DOCKER_SAFETY_BYTES" 10737418240

[ -r "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件不可读：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}
[ -s "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件为空：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}

# 生产传输只信任 CI 提供的 known_hosts；禁止首次连接自动接受未知主机密钥。
ssh_options=(
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE"
  -o "ConnectTimeout=$CONNECT_TIMEOUT_SECONDS"
  -o ConnectionAttempts=2
  -o BatchMode=yes
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
    echo "服务器 SSH 响应正常"
    command -v bash >/dev/null
    echo "服务器 Bash 可用，开始读取 Docker 信息"
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
  local archive_size="$3"
  local required_bytes=$((image_size * 2 + REMOTE_DOCKER_SAFETY_BYTES))

  # 归档先落盘；同盘时还需覆盖归档与 Docker 解包层并存的峰值。
  printf '%s\n%s\n%s\n%s\n' "$image" "$required_bytes" "$archive_size" "$REMOTE_DOCKER_SAFETY_BYTES" | remote_ssh '
    set -eu
    read -r image
    read -r required_bytes
    read -r archive_size
    read -r safety_bytes
    docker_root="$(docker info --format "{{.DockerRootDir}}")"
    set -- $(df -Pk "$docker_root" | awk "NR == 2 { print \$1, \$4 }")
    docker_device="$1"
    available_bytes=$(($2 * 1024))
    set -- $(df -Pk /tmp | awk "NR == 2 { print \$1, \$4 }")
    temp_device="$1"
    temp_available_bytes=$(($2 * 1024))
    if [ "$docker_device" = "$temp_device" ]; then
      required_bytes=$((required_bytes + archive_size))
    fi
    temp_required_bytes=$((archive_size + safety_bytes))
    if [ "$available_bytes" -lt "$required_bytes" ]; then
      echo "服务器 Docker 容量不足：${image}，需要至少 ${required_bytes} 字节，当前可用 ${available_bytes} 字节" >&2
      exit 22
    fi
    if [ "$temp_available_bytes" -lt "$temp_required_bytes" ]; then
      echo "服务器临时目录容量不足：${image}，需要至少 ${temp_required_bytes} 字节，当前可用 ${temp_available_bytes} 字节" >&2
      exit 22
    fi
    echo "服务器 Docker 容量满足要求：${image}，需要 ${required_bytes} 字节，当前可用 ${available_bytes} 字节"
    echo "服务器临时目录容量满足要求：${image}，需要 ${temp_required_bytes} 字节，当前可用 ${temp_available_bytes} 字节"
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

  # 复用只看该服务的完整构建输入集合；共享契约或 Dockerfile 变化同样会强制上传新镜像。
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
        .mvn
        mvnw
        pom.xml
        apps/core-api-java
        packages/service-auth-java
        packages/service-contracts-java
        contracts/core
        contracts/agent-service
        contracts/agent-execution
        apps/core-api-java/src/main/resources/db
        tools/inkforge-cli-java/pom.xml
        infra/docker/core-api.Dockerfile
        infra/docker/inkforge-schema-guard
        infra/docker/inkforge-schema-export
      )
      ;;
    agent-service)
      paths=(
        pyproject.toml
        uv.lock
        .python-version
        packages/service-auth
        packages/service-contracts
        contracts/agent-execution
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
    echo "服务器镜像查询失败：${service}，退出码 ${current_status}" >&2
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
  # 标签不同但内容 ID 相同则只在服务器打标，避免重复传输相同镜像层。
  if server_has_image "$image_id"; then
    server_tag_image "$image_id" "$image"
    echo "复用服务器已有镜像内容：$image"
  else
    image_query_status=$?
    if [ "$image_query_status" -eq 20 ]; then
      images_to_upload+=("$image")
    else
      echo "服务器镜像内容查询失败：${service}，退出码 ${image_query_status}" >&2
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
remote_upload_dir=""
cleanup_upload_archives() {
  local original_status=$?
  if [ -n "$remote_upload_dir" ]; then
    # 只移除本次随机目录里的固定归档，绝不递归清理生产目录。
    if ! printf '%s\n' "$remote_upload_dir" |
      timeout --kill-after=5s 30 ssh "${ssh_options[@]}" "$remote" '
        read -r upload_dir
        rm -f -- "$upload_dir/image.tar.gz" && rmdir -- "$upload_dir"
      '; then
      echo "本次远端镜像临时目录清理失败，残留路径：$remote_upload_dir" >&2
    fi
  fi
  if [ -n "${upload_temp_dir:-}" ] && [ -d "$upload_temp_dir" ]; then
    rm -rf -- "$upload_temp_dir"
  fi
  return "$original_status"
}
# 失败保留原退出码；连接中断时远端残留路径可供运维定位。
trap cleanup_upload_archives EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

remote_directory="$(remote_ssh 'umask 077; mktemp -d /tmp/inkforge-images.XXXXXXXXXX')"
if ! [[ "$remote_directory" =~ ^/tmp/inkforge-images\.[a-zA-Z0-9]+$ ]]; then
  echo "服务器返回了无效的镜像临时目录，停止上传" >&2
  exit 1
fi
remote_upload_dir="$remote_directory"
remote_archive="$remote_upload_dir/image.tar.gz"

stage_failed() {
  local stage="$1"
  local status="$2"
  local limit="$3"
  if [ "$status" -eq 124 ]; then
    echo "镜像${stage}超时：${image}，限制 ${limit} 秒，耗时 $((SECONDS - stage_started)) 秒" >&2
  else
    echo "镜像${stage}失败：${image}，退出码 ${status}，耗时 $((SECONDS - stage_started)) 秒" >&2
  fi
  exit "$status"
}

read_archive_size() {
  local archive="$1"
  local size

  if size="$(stat -c %s "$archive" 2>/dev/null)"; then
    :
  elif size="$(stat -f %z "$archive" 2>/dev/null)"; then
    :
  else
    echo "无法读取镜像归档大小：$archive" >&2
    return 1
  fi
  if [[ ! "$size" =~ ^[0-9]+$ ]]; then
    echo "镜像归档大小不是有效整数：$archive" >&2
    return 1
  fi
  printf '%s\n' "$size"
}

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
      echo "镜像归档超时：${image}，限制 ${IMAGE_ARCHIVE_TIMEOUT_SECONDS} 秒" >&2
    else
      echo "镜像归档失败：${image}，退出码 ${archive_status}" >&2
    fi
    exit "$archive_status"
  fi
  archive_size="$(read_archive_size "$archive")"
  echo "镜像归档完成：${image}，压缩后 ${archive_size} 字节，耗时 $((SECONDS - archive_started)) 秒"

  image_size="$(docker image inspect --format='{{.Size}}' "$image")"
  server_require_capacity "$image" "$image_size" "$archive_size"

  stage_started=$SECONDS
  echo "开始镜像传输：${image}，共 ${archive_size} 字节，超时 ${IMAGE_UPLOAD_TIMEOUT_SECONDS} 秒"
  # 接收端只落盘并输出实际收到的字节进度，不与 Docker 导入争用同一条数据流。
  if timeout --kill-after=30s "$IMAGE_UPLOAD_TIMEOUT_SECONDS" \
    ssh "${ssh_options[@]}" "$remote" \
    "umask 077; dd bs=1M of='$remote_archive' status=progress" < "$archive"; then
    echo "镜像传输完成：${image}，共 ${archive_size} 字节，耗时 $((SECONDS - stage_started)) 秒"
  else
    stage_failed 传输 "$?" "$IMAGE_UPLOAD_TIMEOUT_SECONDS"
  fi

  stage_started=$SECONDS
  echo "开始镜像校验：${image}，SHA-256"
  archive_sha="$(sha256sum "$archive" | cut -d ' ' -f 1)"
  if printf '%s  %s\n' "$archive_sha" "$remote_archive" |
    remote_ssh 'sha256sum --check --status'; then
    echo "镜像校验完成：${image}，SHA-256 一致，耗时 $((SECONDS - stage_started)) 秒"
  else
    stage_failed 校验 "$?" "$REMOTE_COMMAND_TIMEOUT_SECONDS"
  fi

  stage_started=$SECONDS
  echo "开始镜像导入：${image}，超时 ${IMAGE_LOAD_TIMEOUT_SECONDS} 秒"
  # Docker 可直接读取 gzip 归档；远端也设置超时，SSH 断开不会留下无界 load 客户端。
  if printf '%s\n%s\n' "$remote_archive" "$IMAGE_LOAD_TIMEOUT_SECONDS" |
    timeout --kill-after=30s "$((IMAGE_LOAD_TIMEOUT_SECONDS + 60))" \
      ssh "${ssh_options[@]}" "$remote" '
        read -r archive
        read -r load_timeout
        timeout --kill-after=30s "$load_timeout" docker load --input "$archive"
      '; then
    echo "镜像导入完成：${image}，耗时 $((SECONDS - stage_started)) 秒"
  else
    stage_failed 导入 "$?" "$IMAGE_LOAD_TIMEOUT_SECONDS"
  fi

  printf '%s\n' "$remote_archive" | remote_ssh 'read -r archive; rm -f -- "$archive"'
  rm -f -- "$archive"
done
