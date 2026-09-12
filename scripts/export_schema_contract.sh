#!/bin/sh
set -eu

# 使用已构建的 Java Core 执行只读导出；连接配置来自 DATABASE_URL。
jar="${CORE_API_JAR:-apps/core-api-java/target/inkforge-core-api-0.1.0-SNAPSHOT.jar}"
[ -f "$jar" ] || { echo "请先构建 Java Core JAR" >&2; exit 1; }
exec java -Dloader.main=cn.inkforge.core.platform.db.SchemaExportCommand \
  -cp "$jar" org.springframework.boot.loader.launch.PropertiesLauncher "$@"
