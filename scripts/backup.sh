#!/bin/sh
set -eu
umask 077

: "${DATABASE_URL:?必须设置 DATABASE_URL}"
: "${BACKUP_ROOT:?必须设置 BACKUP_ROOT}"

command -v pg_dump >/dev/null 2>&1 || { echo "缺少 pg_dump" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "缺少 sha256sum" >&2; exit 1; }
if [ -n "${EXECUTION_REDIS_CONTAINER:-}" ]; then
  command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_ROOT%/}/inkforge-${stamp}"
[ ! -e "$target" ] || { echo "备份目录已存在，拒绝覆盖" >&2; exit 1; }
mkdir -p "$target"
checksum_files="database.dump recovery-boundary.meta"
journal_snapshot_path=""
execution_journal_included="false"
[ -z "${EXECUTION_REDIS_CONTAINER:-}" ] || execution_journal_included="true"

cleanup_journal_snapshot() {
  if [ -n "$journal_snapshot_path" ] && [ -n "${EXECUTION_REDIS_CONTAINER:-}" ]; then
    docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
      rm -f -- "$journal_snapshot_path" >/dev/null 2>&1 || true
  fi
}
trap cleanup_journal_snapshot EXIT HUP INT TERM

database_url="$(printf '%s' "$DATABASE_URL" | sed 's#postgresql+asyncpg://#postgresql://#')"
pg_dump --format=custom --no-owner --no-acl --file "$target/database.dump" "$database_url"
{
  printf 'format=inkforge-recovery-boundary/1\n'
  printf 'createdAt=%s\n' "$stamp"
  printf 'postgresRestoreRequiresExecutionQuarantine=true\n'
  printf 'executionQuarantineKey=inkforge:executions:restore:quarantine\n'
  printf 'requiresNamedCoreProviderReconciliation=true\n'
  printf 'executionJournalIncluded=%s\n' "$execution_journal_included"
  printf 'restoreWithoutExecutionJournalKeepsProviderCallsFailClosed=true\n'
} > "$target/recovery-boundary.meta"

if [ -n "${UPLOADS_PATH:-}" ]; then
  [ -d "$UPLOADS_PATH" ] || { echo "上传目录不存在" >&2; exit 1; }
  tar -C "$UPLOADS_PATH" -czf "$target/uploads.tar.gz" .
  checksum_files="$checksum_files uploads.tar.gz"
fi

if [ -n "${EXECUTION_REDIS_CONTAINER:-}" ]; then
  case "$EXECUTION_REDIS_CONTAINER" in
    *[!A-Za-z0-9_.-]*|'') echo "execution Redis 容器名无效" >&2; exit 1 ;;
  esac
  journal_snapshot_path="/data/.inkforge-journal-backup-${stamp}.rdb"
  persistence_info="$(
    docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
      redis-cli --raw INFO persistence
  )"
  printf '%s\n' "$persistence_info" | grep -q '^aof_enabled:1' || {
    echo "execution Redis 未启用 AOF，拒绝备份" >&2
    exit 1
  }
  printf '%s\n' "$persistence_info" | grep -q '^aof_last_write_status:ok' || {
    echo "execution Redis AOF 写状态异常，拒绝备份" >&2
    exit 1
  }
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-cli --rdb "$journal_snapshot_path" >/dev/null
  docker exec --user 999:999 "$EXECUTION_REDIS_CONTAINER" \
    redis-check-rdb "$journal_snapshot_path" >/dev/null
  docker cp \
    "$EXECUTION_REDIS_CONTAINER:$journal_snapshot_path" \
    "$target/execution-journal.rdb"
  snapshot_sha256="$(sha256sum "$target/execution-journal.rdb" | cut -d ' ' -f 1)"
  {
    printf 'format=inkforge-execution-journal-backup/1\n'
    printf 'createdAt=%s\n' "$stamp"
    printf 'snapshotSha256=%s\n' "$snapshot_sha256"
    printf 'restoreQuarantineKey=inkforge:executions:restore:quarantine\n'
    printf 'restoreRequiresNamedReconciliation=true\n'
  } > "$target/execution-journal.meta"
  checksum_files="$checksum_files execution-journal.rdb execution-journal.meta"
  cleanup_journal_snapshot
  journal_snapshot_path=""
fi

(cd "$target" && sha256sum $checksum_files > SHA256SUMS)
trap - EXIT HUP INT TERM
echo "备份完成：$target"
