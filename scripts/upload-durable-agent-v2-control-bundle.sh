#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${SERVER_HOST:?必须设置服务器地址}"
: "${SERVER_USER:?必须设置服务器用户}"
: "${SSH_KEY_PATH:?必须设置 SSH 私钥路径}"
: "${SSH_KNOWN_HOSTS_FILE:?必须设置 known_hosts 文件路径}"
: "${APP_DIR:?必须设置服务器 APP_DIR}"
: "${CONTROL_BUNDLE_DIR:?必须设置本地 control bundle 目录}"
: "${CONTROL_BUNDLE_SHA256:?必须设置 control bundle SHA-256}"
: "${WORKFLOW_TRUSTED_COMMIT:?必须设置 workflow trusted commit}"
: "${TARGET_RELEASE_COMMIT:?必须设置 target release commit}"

case "$APP_DIR" in
  /*) ;;
  *) echo "服务器 APP_DIR 必须是绝对路径" >&2; exit 1 ;;
esac
case "$APP_DIR" in
  *[!A-Za-z0-9_./-]*|*/../*|*/..|*/./*) echo "服务器 APP_DIR 路径无效" >&2; exit 1 ;;
esac
for commit in "$WORKFLOW_TRUSTED_COMMIT" "$TARGET_RELEASE_COMMIT"; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "control bundle commit 无效" >&2; exit 1; }
done
[[ "$CONTROL_BUNDLE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
  echo "control bundle SHA-256 无效" >&2
  exit 1
}
[[ "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ]] || { echo "GitHub run ID 无效" >&2; exit 1; }
[[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[1-9][0-9]*$ ]] || {
  echo "GitHub run attempt 无效" >&2
  exit 1
}

helper="$(pwd)/scripts/durable_agent_v2_control_bundle.py"
[ -r "$helper" ] && [ -r "$SSH_KEY_PATH" ] \
  && [ -s "$SSH_KNOWN_HOSTS_FILE" ] || {
    echo "control bundle 上传输入缺失" >&2
    exit 1
  }
python3 "$helper" verify --bundle-dir "$CONTROL_BUNDLE_DIR" \
  --expected-sha256 "$CONTROL_BUNDLE_SHA256" >/dev/null
helper_sha="$(sha256sum "$helper" | cut -d ' ' -f 1)"

ssh_options=(
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE"
  -o ConnectTimeout=15
  -o ConnectionAttempts=2
  -o BatchMode=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=20
  -o TCPKeepAlive=yes
  -i "$SSH_KEY_PATH"
)
remote="${SERVER_USER}@${SERVER_HOST}"
remote_root="${APP_DIR%/}/.durable-agent-v2-control-bundles/${WORKFLOW_TRUSTED_COMMIT}"
remote_final="${remote_root}/${CONTROL_BUNDLE_SHA256}"
remote_partial="${remote_root}/.${CONTROL_BUNDLE_SHA256}.partial.${GITHUB_RUN_ID}.${GITHUB_RUN_ATTEMPT}"

remote_ssh() {
  timeout --kill-after=30s 180 ssh "${ssh_options[@]}" "$remote" "$@"
}

verify_remote() {
  printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
    "$1" "$CONTROL_BUNDLE_SHA256" "$helper_sha" \
    "$WORKFLOW_TRUSTED_COMMIT" "$TARGET_RELEASE_COMMIT" \
    "$GITHUB_RUN_ID:$GITHUB_RUN_ATTEMPT" | remote_ssh '
      set -eu
      read -r bundle
      read -r expected_bundle_sha
      read -r expected_helper_sha
      read -r expected_workflow
      read -r expected_target
      read -r expected_run
      [ -d "$bundle" ] && [ ! -L "$bundle" ]
      [ "$(stat -c %a "$bundle")" = 700 ]
      helper="$bundle/scripts/durable_agent_v2_control_bundle.py"
      [ -f "$helper" ] && [ ! -L "$helper" ]
      [ "$(sha256sum "$helper" | cut -d " " -f 1)" = "$expected_helper_sha" ]
      output="$(python3 "$helper" verify --bundle-dir "$bundle" --expected-sha256 "$expected_bundle_sha")"
      [ "$output" = "control-bundle-verified:$expected_bundle_sha" ]
      python3 - "$bundle/control-bundle.json" "$expected_workflow" "$expected_target" "$expected_run" <<"PY"
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
run_id, run_attempt = sys.argv[4].split(":", 1)
expected = {
    "workflowTrustedCommit": sys.argv[2],
    "targetReleaseCommit": sys.argv[3],
    "producerRunId": run_id,
    "producerRunAttempt": run_attempt,
}
if any(document.get(key) != value for key, value in expected.items()):
    raise SystemExit("control-bundle-provenance")
PY
    '
}

if verify_remote "$remote_final" >/dev/null 2>&1; then
  printf 'control-bundle-upload-ok:%s\n' "$remote_final"
  exit 0
fi

printf '%s\n%s\n' "$remote_root" "$remote_partial" | remote_ssh '
  set -eu
  umask 077
  read -r root
  read -r partial
  mkdir -p "$root"
  chmod 700 "${root%/*}" "$root"
  [ ! -e "$partial" ]
'

timeout --kill-after=30s 600 scp "${ssh_options[@]}" -r \
  "$CONTROL_BUNDLE_DIR" "${remote}:${remote_partial}"

printf '%s\n' "$remote_partial" | remote_ssh '
  set -eu
  read -r partial
  find "$partial" -type d -exec chmod 700 {} +
  find "$partial" -type f -exec chmod 600 {} +
'
verify_remote "$remote_partial"

printf '%s\n%s\n%s\n' "$remote_partial" "$remote_final" \
  "$CONTROL_BUNDLE_SHA256" | remote_ssh '
  set -eu
  read -r partial
  read -r final
  read -r expected_sha
  helper="$partial/scripts/durable_agent_v2_control_bundle.py"
  output="$(python3 "$helper" publish --bundle-dir "$partial" \
    --target-dir "$final" --expected-sha256 "$expected_sha")"
  [ "$output" = "control-bundle-published:$expected_sha" ]
  [ ! -e "$partial" ] && [ -d "$final" ]
'
verify_remote "$remote_final"
printf 'control-bundle-upload-ok:%s\n' "$remote_final"
