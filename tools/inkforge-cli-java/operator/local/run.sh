#!/bin/sh
# 只启动已配置的 Java 运行包；保持标准流、真实终端和信号语义。
set -eu
state_root="${HOME}/Library/Application Support/InkForge/codex-operator"
if [ "${1:-}" = "--state-root" ]; then
  if [ "$#" -lt 2 ] || [ -z "$2" ]; then
    echo '缺少 --state-root 路径' >&2
    exit 2
  fi
  state_root=$2
  shift 2
fi
if [ ! -x "$state_root/runtime/java" ] || [ ! -f "$state_root/runtime/inkforge-cli.jar" ]; then
  echo 'Java CLI 尚未配置，请先运行本 Skill 的 scripts/configure.sh。' >&2
  exit 2
fi
exec "$state_root/runtime/java" -cp "$state_root/runtime/inkforge-cli.jar" \
  cn.inkforge.cli.operator.OperatorMain local --state-root "$state_root" "$@"
