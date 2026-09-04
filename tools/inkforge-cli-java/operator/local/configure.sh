#!/bin/sh
# 安装已构建的 Java CLI；不联网、不自动构建、不读取业务凭据。
set -eu
repository_root=
java_path=
expected_username=
state_root=
while [ "$#" -gt 0 ]; do
  if [ "$#" -lt 2 ] || [ -z "$2" ]; then
    echo '配置参数必须提供非空值。' >&2
    exit 2
  fi
  case "$1" in
    --repository-root) repository_root=$2 ;;
    --java-path) java_path=$2 ;;
    --expected-username) expected_username=$2 ;;
    --state-root) state_root=$2 ;;
    *) echo '未知配置参数。' >&2; exit 2 ;;
  esac
  shift 2
done
if [ -z "$repository_root" ]; then
  echo '请提供 --repository-root，指向已构建 Java CLI 的仓库。' >&2
  exit 2
fi
if [ -z "$java_path" ]; then
  if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
    java_path="$JAVA_HOME/bin/java"
  elif [ -x /usr/libexec/java_home ] && java_home=$(/usr/libexec/java_home -v 21 2>/dev/null); then
    java_path="$java_home/bin/java"
  elif [ -x /opt/homebrew/opt/openjdk@21/bin/java ]; then
    java_path=/opt/homebrew/opt/openjdk@21/bin/java
  elif [ -x /usr/local/opt/openjdk@21/bin/java ]; then
    java_path=/usr/local/opt/openjdk@21/bin/java
  else
    echo '未找到 Java 21，请提供 --java-path。' >&2
    exit 2
  fi
fi
if [ ! -x "$java_path" ]; then
  echo 'Java executable 不存在或不可执行。' >&2
  exit 2
fi
jar_path="$repository_root/tools/inkforge-cli-java/target/inkforge-cli.jar"
if [ ! -f "$jar_path" ]; then
  echo '未找到已构建的 inkforge-cli.jar；请先按 CLI 文档构建。' >&2
  exit 2
fi
set -- local configure --repository-root "$repository_root"
if [ -n "$expected_username" ]; then set -- "$@" --expected-username "$expected_username"; fi
if [ -n "$state_root" ]; then set -- "$@" --state-root "$state_root"; fi
exec "$java_path" -cp "$jar_path" cn.inkforge.cli.operator.OperatorMain "$@"
