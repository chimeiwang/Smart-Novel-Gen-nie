#!/bin/sh
set -eu

: "${BACKUP_DIR:?必须设置 BACKUP_DIR}"
: "${VERIFY_DATABASE_URL:?必须设置独立验证数据库地址}"
: "${DATABASE_URL:?必须设置生产数据库地址用于防误操作比较}"
[ "${ALLOW_RESTORE_VERIFY:-no}" = "yes" ] || { echo "必须设置 ALLOW_RESTORE_VERIFY=yes" >&2; exit 1; }
[ "$VERIFY_DATABASE_URL" != "$DATABASE_URL" ] || { echo "验证数据库不得与生产数据库相同" >&2; exit 1; }

command -v pg_restore >/dev/null 2>&1 || { echo "缺少 pg_restore" >&2; exit 1; }
[ -f "$BACKUP_DIR/database.dump" ] || { echo "缺少数据库备份" >&2; exit 1; }
(cd "$BACKUP_DIR" && sha256sum --check SHA256SUMS)

verify_url="$(printf '%s' "$VERIFY_DATABASE_URL" | sed 's#postgresql+asyncpg://#postgresql://#')"
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$verify_url" "$BACKUP_DIR/database.dump"

if [ -f "$BACKUP_DIR/uploads.tar.gz" ]; then
  tar -tzf "$BACKUP_DIR/uploads.tar.gz" >/dev/null
fi

DATABASE_URL="$VERIFY_DATABASE_URL" scripts/schema_fingerprint.sh
echo "独立验证库恢复检查通过"
