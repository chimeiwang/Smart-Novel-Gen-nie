#!/bin/sh
# 真实 shaded JAR 与 shell 接线的离线测试；只使用隔离配置，不读取用户凭据或联网。
set -eu
if [ "$#" -ne 2 ]; then
  echo '用法：test-launchers.sh <仓库绝对路径> <Java 21 executable>' >&2
  exit 2
fi
repository_root=$1
java_path=$2
test_root=$(mktemp -d /tmp/inkforge-java-operator-test.XXXXXX)
test_root=$(cd "$test_root" && pwd -P)
trap 'test_result=$?; trap - EXIT; rm -r "$test_root"; exit "$test_result"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
for mode in local production; do
  state_root="$test_root/$mode state"
  scripts_root="$repository_root/tools/inkforge-cli-java/operator/$mode"
  "$scripts_root/configure.sh" --repository-root "$repository_root" \
    --java-path "$java_path" --state-root "$state_root" --expected-username '离线验收用户😀' \
    > "$test_root/configure-$mode.out"
  test -x "$state_root/runtime/java"
  test -s "$state_root/runtime/inkforge-cli.jar"
  cmp "$state_root/runtime/inkforge-cli.jar" \
    "$repository_root/tools/inkforge-cli-java/target/inkforge-cli.jar"
  # 清空其他运行工具路径，并隔离 CLI 的 user.home，确保不会读取真实 profile 或 Keychain。
  set +e
  output=$(printf '%s' '{}' | env PATH=/usr/bin:/bin \
    JAVA_TOOL_OPTIONS="-Duser.home=$test_root" \
    "$scripts_root/run.sh" --state-root "$state_root" auth.whoami 2> "$test_root/error-$mode.out")
  result=$?
  set -e
  test "$result" -eq 3
  case "$output" in *'AUTH_REQUIRED'*) ;; *) echo '缺少 profile 应返回 AUTH_REQUIRED。' >&2; exit 1 ;; esac
  set +e
  output=$(printf '%s' '{}' | "$scripts_root/run.sh" --state-root "$state_root" long.video.project.list 2>&1)
  result=$?
  set -e
  test "$result" -eq 2
  case "$output" in *'OPERATOR_COMMAND_NOT_ALLOWED'*) ;; *) echo '未开放命令未被拒绝。' >&2; exit 1 ;; esac
  set +e
  output=$(printf '%s' '{"Origin":"https://example.invalid"}' | \
    "$scripts_root/run.sh" --state-root "$state_root" auth.whoami 2>&1)
  result=$?
  set -e
  test "$result" -eq 2
  # 安装包被改变后必须停止，不能读取真实身份或继续业务调用。
  printf '\n' >> "$state_root/runtime/inkforge-cli.jar"
  set +e
  output=$(printf '%s' '{}' | "$scripts_root/run.sh" --state-root "$state_root" auth.whoami 2>&1)
  result=$?
  set -e
  test "$result" -eq 3
  echo "${mode}：配置安装、无 Python/uv 启动、缺会话、白名单、端点绑定和包校验通过。"
done
