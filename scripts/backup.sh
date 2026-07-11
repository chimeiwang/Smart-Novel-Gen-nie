#!/bin/sh
set -eu

: "${DATABASE_URL:?必须设置 DATABASE_URL}"
: "${BACKUP_ROOT:?必须设置 BACKUP_ROOT}"

command -v pg_dump >/dev/null 2>&1 || { echo "缺少 pg_dump" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "缺少 sha256sum" >&2; exit 1; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_ROOT%/}/inkforge-${stamp}"
[ ! -e "$target" ] || { echo "备份目录已存在，拒绝覆盖" >&2; exit 1; }
mkdir -p "$target"

database_url="$(printf '%s' "$DATABASE_URL" | sed 's#postgresql+asyncpg://#postgresql://#')"
pg_dump --format=custom --no-owner --no-acl --file "$target/database.dump" "$database_url"

if [ -n "${UPLOADS_PATH:-}" ]; then
  [ -d "$UPLOADS_PATH" ] || { echo "上传目录不存在" >&2; exit 1; }
  tar -C "$UPLOADS_PATH" -czf "$target/uploads.tar.gz" .
fi

(cd "$target" && sha256sum database.dump ${UPLOADS_PATH:+uploads.tar.gz} > SHA256SUMS)
echo "备份完成：$target"
