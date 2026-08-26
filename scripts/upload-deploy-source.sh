#!/usr/bin/env bash
set -euo pipefail

: "${SERVER_HOST:?必须设置服务器地址}"
: "${SERVER_USER:?必须设置服务器用户}"
: "${SSH_KEY_PATH:?必须设置 SSH 私钥路径}"
: "${SSH_KNOWN_HOSTS_FILE:?必须设置 known_hosts 文件路径}"
DEPLOY_SHA="${DEPLOY_SHA:?必须设置部署提交}"

SOURCE_UPLOAD_TIMEOUT_SECONDS="${SOURCE_UPLOAD_TIMEOUT_SECONDS:-600}"
REMOTE_COMMAND_TIMEOUT_SECONDS="${REMOTE_COMMAND_TIMEOUT_SECONDS:-120}"
SOURCE_UPLOAD_ATTEMPTS="${SOURCE_UPLOAD_ATTEMPTS:-3}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-15}"

validate_positive_integer() {
  local name="$1"
  local value="$2"
  local maximum="$3"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]] || [ "$value" -gt "$maximum" ]; then
    echo "$name 必须是 1 到 $maximum 之间的整数，当前值：$value" >&2
    exit 1
  fi
}

case "$DEPLOY_SHA" in
  ""|*[!0-9a-f]*)
    echo "部署提交必须是 40 位小写十六进制 SHA" >&2
    exit 1
    ;;
esac
[ "${#DEPLOY_SHA}" -eq 40 ] || {
  echo "部署提交必须是 40 位小写十六进制 SHA" >&2
  exit 1
}

validate_positive_integer SOURCE_UPLOAD_TIMEOUT_SECONDS "$SOURCE_UPLOAD_TIMEOUT_SECONDS" 1800
validate_positive_integer REMOTE_COMMAND_TIMEOUT_SECONDS "$REMOTE_COMMAND_TIMEOUT_SECONDS" 600
validate_positive_integer SOURCE_UPLOAD_ATTEMPTS "$SOURCE_UPLOAD_ATTEMPTS" 5
validate_positive_integer CONNECT_TIMEOUT_SECONDS "$CONNECT_TIMEOUT_SECONDS" 120

[ -r "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件不可读：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}
[ -s "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件为空：$SSH_KNOWN_HOSTS_FILE" >&2
  exit 1
}

for command_name in git ssh scp timeout; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "缺少部署源码上传命令：$command_name" >&2
    exit 1
  }
done

# 源码与镜像使用同一份 CI 固定主机身份；不得为传输 bundle 降级主机校验。
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
remote_bundle="/tmp/inkforge-deploy-${DEPLOY_SHA}.bundle"
remote_partial="${remote_bundle}.partial"

local_temp_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/inkforge-source.XXXXXX")"
local_bundle="$local_temp_dir/source.bundle"
cleanup_local_bundle() {
  if [ -n "${local_temp_dir:-}" ] && [ -d "$local_temp_dir" ]; then
    rm -rf -- "$local_temp_dir"
  fi
}
trap cleanup_local_bundle EXIT

head_sha="$(git rev-parse HEAD)"
[ "$head_sha" = "$DEPLOY_SHA" ] || {
  echo "CI checkout 与部署提交不一致" >&2
  exit 1
}

# HEAD bundle 只包含目标提交可达历史，不读取工作区未提交文件，也不会携带部署环境秘密。
git bundle create "$local_bundle" HEAD --
git bundle verify "$local_bundle"
chmod 600 "$local_bundle"
bundle_sha="$(git bundle list-heads "$local_bundle" HEAD | awk '$2 == "HEAD" { print $1 }')"
[ "$bundle_sha" = "$DEPLOY_SHA" ] || {
  echo "部署源码 bundle 的 HEAD 与部署提交不一致" >&2
  exit 1
}

remote_ssh() {
  timeout --kill-after=30s "$REMOTE_COMMAND_TIMEOUT_SECONDS" \
    ssh "${ssh_options[@]}" "$remote" "$@"
}

cleanup_remote_partial() {
  remote_ssh "rm -f -- '$remote_partial'" >/dev/null 2>&1 || true
}

upload_once() {
  # scp 只写 .partial；完整传输后再在服务器同目录原子改名，部署脚本绝不会读取半包。
  timeout --kill-after=30s "$SOURCE_UPLOAD_TIMEOUT_SECONDS" \
    scp "${ssh_options[@]}" -p "$local_bundle" "${remote}:${remote_partial}" || return $?
  remote_ssh "chmod 600 '$remote_partial' && mv -f -- '$remote_partial' '$remote_bundle'"
}

upload_attempt=1
while :; do
  if upload_once; then
    break
  else
    upload_status=$?
  fi
  cleanup_remote_partial
  if [ "$upload_status" -ne 255 ]; then
    if [ "$upload_status" -eq 124 ]; then
      echo "部署源码 bundle 上传超时，限制 ${SOURCE_UPLOAD_TIMEOUT_SECONDS} 秒" >&2
    else
      echo "部署源码 bundle 上传失败，退出码 ${upload_status}" >&2
    fi
    exit "$upload_status"
  fi
  if [ "$upload_attempt" -ge "$SOURCE_UPLOAD_ATTEMPTS" ]; then
    echo "部署源码 bundle 上传连续失败 ${SOURCE_UPLOAD_ATTEMPTS} 次" >&2
    exit "$upload_status"
  fi
  next_attempt=$((upload_attempt + 1))
  echo "部署源码 bundle 上传失败，等待后重试第 ${next_attempt}/${SOURCE_UPLOAD_ATTEMPTS} 次" >&2
  sleep $((upload_attempt * 3))
  upload_attempt="$next_attempt"
done

echo "部署源码 bundle 已上传：$remote_bundle"
