#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${SERVER_HOST:?必须设置服务器地址}"
: "${SERVER_USER:?必须设置服务器用户}"
: "${SSH_KEY_PATH:?必须设置 SSH 私钥路径}"
: "${SSH_KNOWN_HOSTS_FILE:?必须设置 known_hosts 文件路径}"
: "${APP_DIR:?必须设置服务器 APP_DIR}"
: "${TARGET_RELEASE_COMMIT:?必须设置 target release commit}"
: "${RELEASE_MANIFEST_SHA256:?必须设置 release manifest SHA-256}"
: "${RELEASE_MANIFEST_DIR:?必须设置 release manifest 目录}"
MANIFEST_FACTS_ROOT="${MANIFEST_FACTS_ROOT:-$(pwd)}"

CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-15}"
REMOTE_COMMAND_TIMEOUT_SECONDS="${REMOTE_COMMAND_TIMEOUT_SECONDS:-120}"
MANIFEST_UPLOAD_TIMEOUT_SECONDS="${MANIFEST_UPLOAD_TIMEOUT_SECONDS:-180}"

case "$TARGET_RELEASE_COMMIT" in
  ""|*[!0-9a-f]*) echo "target release commit 格式无效" >&2; exit 1 ;;
esac
[ "${#TARGET_RELEASE_COMMIT}" -eq 40 ] || {
  echo "target release commit 格式无效" >&2
  exit 1
}
case "$RELEASE_MANIFEST_SHA256" in
  ""|*[!0-9a-f]*) echo "release manifest SHA-256 格式无效" >&2; exit 1 ;;
esac
[ "${#RELEASE_MANIFEST_SHA256}" -eq 64 ] || {
  echo "release manifest SHA-256 格式无效" >&2
  exit 1
}
case "$APP_DIR" in
  /*) ;;
  *) echo "服务器 APP_DIR 必须是绝对路径" >&2; exit 1 ;;
esac
case "$APP_DIR" in
  *[!A-Za-z0-9_./-]*|*/../*|*/..|*/./*) echo "服务器 APP_DIR 路径无效" >&2; exit 1 ;;
esac
for value in "$CONNECT_TIMEOUT_SECONDS" "$REMOTE_COMMAND_TIMEOUT_SECONDS" \
  "$MANIFEST_UPLOAD_TIMEOUT_SECONDS"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo "上传超时参数无效" >&2; exit 1; }
done
[ "$CONNECT_TIMEOUT_SECONDS" -le 120 ] \
  && [ "$REMOTE_COMMAND_TIMEOUT_SECONDS" -le 600 ] \
  && [ "$MANIFEST_UPLOAD_TIMEOUT_SECONDS" -le 600 ] || {
    echo "上传超时参数超过上限" >&2
    exit 1
  }

manifest_helper="$(pwd)/scripts/durable_agent_v2_release_manifest.py"
[ -r "$manifest_helper" ] || { echo "缺少 release manifest helper" >&2; exit 1; }
[ -r "$SSH_KNOWN_HOSTS_FILE" ] && [ -s "$SSH_KNOWN_HOSTS_FILE" ] || {
  echo "known_hosts 文件缺失或为空" >&2
  exit 1
}
[ -r "$SSH_KEY_PATH" ] || { echo "SSH 私钥不可读" >&2; exit 1; }
for command_name in python3 sha256sum ssh scp timeout; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "缺少 manifest 上传命令：$command_name" >&2
    exit 1
  }
done

verify_output="$(python3 "$manifest_helper" verify \
  --repository-root "$MANIFEST_FACTS_ROOT" \
  --manifest-dir "$RELEASE_MANIFEST_DIR" \
  --expected-target-commit "$TARGET_RELEASE_COMMIT" \
  --expected-artifact-sha256 "$RELEASE_MANIFEST_SHA256")"
case "$verify_output" in
  release-manifest-verified:*) manifest_sha="${verify_output#release-manifest-verified:}" ;;
  *) echo "release manifest helper 输出无效" >&2; exit 1 ;;
esac
case "$manifest_sha" in ""|*[!0-9a-f]*) exit 1 ;; esac
[ "${#manifest_sha}" -eq 64 ] || exit 1
[ "$manifest_sha" = "$RELEASE_MANIFEST_SHA256" ] || exit 1

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
remote_root="${APP_DIR%/}/.durable-agent-v2-release-manifests"
remote_final="$remote_root/$manifest_sha"
remote_partial="$remote_root/.${manifest_sha}.partial.${GITHUB_RUN_ID:-local}.${GITHUB_RUN_ATTEMPT:-1}"
case "$remote_partial" in *[!A-Za-z0-9_./-]*) echo "远程临时路径无效" >&2; exit 1 ;; esac

remote_ssh() {
  timeout --kill-after=30s "$REMOTE_COMMAND_TIMEOUT_SECONDS" \
    ssh "${ssh_options[@]}" "$remote" "$@"
}

if printf '%s\n%s\n' "$remote_final" "$manifest_sha" | remote_ssh '
  set -eu
  read -r final
  read -r expected_sha
  [ -d "$final" ] || exit 20
  [ ! -L "$final" ]
  [ "$(stat -c %a "$final")" = 700 ]
  [ "$(stat -c %a "$final/release-manifest.json")" = 600 ]
  [ "$(stat -c %a "$final/SHA256SUMS")" = 600 ]
  [ "$(sha256sum "$final/release-manifest.json" | cut -d " " -f 1)" = "$expected_sha" ]
  [ "$(cat "$final/SHA256SUMS")" = "$expected_sha  release-manifest.json" ]
'; then
  printf 'release-manifest-upload-ok:%s\n' "$remote_final"
  exit 0
else
  existing_status=$?
  [ "$existing_status" -eq 20 ] || {
    echo "服务器已有 release manifest 目录但无法精确复验" >&2
    exit 1
  }
fi

printf '%s\n%s\n' "$remote_root" "$remote_partial" | remote_ssh '
  set -eu
  umask 077
  read -r root
  read -r partial
  mkdir -p "$root"
  chmod 700 "$root"
  [ ! -e "$partial" ]
  mkdir "$partial"
  chmod 700 "$partial"
'

cleanup_remote_partial() {
  printf '%s\n' "$remote_partial" | remote_ssh '
    read -r partial
    case "$partial" in */.????????????????????????????????????????????????????????????????.partial.*)
      rm -f -- "$partial/release-manifest.json" "$partial/SHA256SUMS"
      rmdir -- "$partial" 2>/dev/null || true
      ;;
    esac
  ' >/dev/null 2>&1 || true
}
trap cleanup_remote_partial EXIT

timeout --kill-after=30s "$MANIFEST_UPLOAD_TIMEOUT_SECONDS" \
  scp "${ssh_options[@]}" \
    "$RELEASE_MANIFEST_DIR/release-manifest.json" \
    "$RELEASE_MANIFEST_DIR/SHA256SUMS" \
    "${remote}:${remote_partial}/"

printf '%s\n%s\n%s\n' "$remote_partial" "$remote_final" "$manifest_sha" | remote_ssh '
  set -eu
  read -r partial
  read -r final
  read -r expected_sha
  chmod 600 "$partial/release-manifest.json" "$partial/SHA256SUMS"
  [ "$(sha256sum "$partial/release-manifest.json" | cut -d " " -f 1)" = "$expected_sha" ]
  [ "$(cat "$partial/SHA256SUMS")" = "$expected_sha  release-manifest.json" ]
  mv -T -n "$partial" "$final"
  [ ! -e "$partial" ] && [ -d "$final" ]
'

trap - EXIT
printf 'release-manifest-upload-ok:%s\n' "$remote_final"
