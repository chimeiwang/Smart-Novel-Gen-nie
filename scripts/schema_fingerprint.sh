#!/bin/sh
set -eu

# 恢复验证显式提供数据库时必须核对该库，不能退回活动 Core 的生产连接。
if [ -n "${DATABASE_URL:-}" ]; then
  [ "$#" -eq 0 ] || { echo "不能同时指定数据库与 Core 容器" >&2; exit 2; }
  jar="${CORE_API_JAR:-apps/core-api-java/target/inkforge-core-api-0.1.0-SNAPSHOT.jar}"
  [ -f "$jar" ] || { echo "验证指定数据库前必须先构建 Java Core JAR" >&2; exit 1; }
  exec java -Dloader.main=cn.inkforge.core.platform.db.SchemaGuardCommand \
    -cp "$jar" org.springframework.boot.loader.launch.PropertiesLauncher
fi
# 无显式数据库时，复用独立受限容器检查当前 Core，避免在活动容器内启动第二个 JVM。
container="${1:-$(docker compose --env-file "${COMPOSE_ENV_FILE:-.env}" -f infra/compose.yaml ps -q core-api)}"
[ -n "$container" ] || { echo "未找到 Core 容器" >&2; exit 1; }
exec sh scripts/verify-running-core-schema.sh "$container"
