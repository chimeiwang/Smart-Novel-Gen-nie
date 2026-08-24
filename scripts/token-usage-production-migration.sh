#!/bin/sh
set -eu
umask 077

action="${1:-}"
app_dir="${APP_DIR:-$(pwd)}"
env_file="$app_dir/.env"
forward_sql="$app_dir/scripts/migrations/20260823_token_usage_details.production.sql"
rollback_sql="$app_dir/scripts/migrations/rollback_20260823_token_usage_details.sql"
forward_sha="BC5D7B708E5DBA4EE81E31D21C9E2087AFB87D0582C916A0FA9E3C529994FAF5"
rollback_sha="D00EF3B1FD299BEBAB644C758678ACF0FF7C3C6F0855199D56FA10B9008A19FE"

case "$action" in
  status|backup|up|down) ;;
  *) echo "生产 TokenUsage 迁移动作无效" >&2; exit 2 ;;
esac

for command_name in python3 psql pg_dump pg_restore sha256sum timeout mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "生产 TokenUsage 迁移缺少必要命令" >&2
    exit 1
  }
done
[ -r "$env_file" ] || { echo "生产环境文件不可读" >&2; exit 1; }
[ -r "$forward_sql" ] || { echo "固定生产迁移 SQL 不可读" >&2; exit 1; }
[ -r "$rollback_sql" ] || { echo "固定生产回退 SQL 不可读" >&2; exit 1; }

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/inkforge-token-usage-production.XXXXXX")"
case "$temp_dir" in
  "${TMPDIR:-/tmp}"/inkforge-token-usage-production.*) ;;
  *) echo "生产迁移临时目录不符合固定约定" >&2; exit 1 ;;
esac
pgpass_file="$temp_dir/pgpass"
cleanup() {
  rm -f -- "$pgpass_file"
  rmdir -- "$temp_dir" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

set +x
database_url="$(python3 - "$env_file" "$pgpass_file" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

SAFE_QUERY_KEYS = {"application_name", "sslmode"}


class DatabaseUrlRejected(Exception):
    pass


def escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def parse_database_url(env_path: str, pgpass_path: str) -> str:
    matches: list[str] = []
    for raw_line in Path(env_path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("DATABASE_URL="):
            value = line[len("DATABASE_URL=") :].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1].strip()
            matches.append(value)
    if len(matches) != 1 or not matches[0]:
        raise DatabaseUrlRejected("database_url_count")
    value = matches[0]
    normalized = (
        "postgresql://" + value[len("postgresql+asyncpg://") :]
        if value.startswith("postgresql+asyncpg://")
        else value
    )
    try:
        parts = urlsplit(normalized)
    except ValueError:
        raise DatabaseUrlRejected("url_split") from None
    if parts.scheme != "postgresql" or not parts.netloc:
        raise DatabaseUrlRejected("scheme_or_authority")
    if parts.path != "/novelwriter":
        raise DatabaseUrlRejected("source_database")
    if parts.fragment:
        raise DatabaseUrlRejected("fragment")
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query_keys = [key for key, _value in query_pairs]
    if len(query_keys) != len(set(query_keys)) or any(
        key not in SAFE_QUERY_KEYS for key in query_keys
    ):
        raise DatabaseUrlRejected("query")
    username = unquote(parts.username or "")
    password = unquote(parts.password or "")
    hostname = parts.hostname or ""
    try:
        port = parts.port or 5432
    except ValueError:
        raise DatabaseUrlRejected("port") from None
    if not username or not password or not hostname:
        raise DatabaseUrlRejected("credentials")
    if hostname != "host.docker.internal":
        raise DatabaseUrlRejected("source_host")
    if any("\n" in item or "\r" in item for item in (username, password, hostname)):
        raise DatabaseUrlRejected("newline")
    command_hostname = "127.0.0.1"
    pgpass = ":".join(
        escape_pgpass(item)
        for item in (command_hostname, str(port), "novelwriter", username, password)
    ) + "\n"
    descriptor = os.open(pgpass_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
        target.write(pgpass)
    safe_netloc = f"{quote(username, safe='')}@{command_hostname}"
    if parts.port is not None:
        safe_netloc += f":{parts.port}"
    return urlunsplit(parts._replace(netloc=safe_netloc))


try:
    print(parse_database_url(sys.argv[1], sys.argv[2]), end="")
except DatabaseUrlRejected as exc:
    print(f"database-url-check:{exc}", file=sys.stderr)
    raise SystemExit(1) from None
except (OSError, UnicodeError, ValueError):
    print("database-url-check:invalid", file=sys.stderr)
    raise SystemExit(1) from None
PY
)" || { echo "生产 DATABASE_URL 安全解析失败" >&2; exit 1; }
[ -s "$pgpass_file" ] || { echo "生产数据库凭据文件未生成" >&2; exit 1; }
chmod 600 "$pgpass_file"
PGPASSFILE="$pgpass_file"
export PGPASSFILE

query_schema_state() {
  state="$(PGOPTIONS='-c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -v ON_ERROR_STOP=1 -Atq "$database_url" <<'SQL'
BEGIN;
CREATE TEMP TABLE token_usage_details_constraint_contract (
    "promptCacheMissTokens" INTEGER,
    "reasoningTokens" INTEGER,
    "cachedTokens" INTEGER NOT NULL,
    "promptTokens" INTEGER NOT NULL,
    "completionTokens" INTEGER NOT NULL
) ON COMMIT DROP;
ALTER TABLE pg_temp.token_usage_details_constraint_contract
    ADD CONSTRAINT "TokenUsage_token_details_nonnegative_check"
    CHECK (("promptCacheMissTokens" IS NULL OR "promptCacheMissTokens" >= 0)
        AND ("reasoningTokens" IS NULL OR "reasoningTokens" >= 0)),
    ADD CONSTRAINT "TokenUsage_prompt_cache_details_check"
    CHECK ("promptCacheMissTokens" IS NULL OR
        "cachedTokens" + "promptCacheMissTokens" = "promptTokens"),
    ADD CONSTRAINT "TokenUsage_reasoning_details_check"
    CHECK ("reasoningTokens" IS NULL OR
        "reasoningTokens" <= "completionTokens");
WITH target_table AS (
    SELECT to_regclass('public."TokenUsage"') AS table_oid
), column_state AS (
    SELECT
        count(attribute.attname) AS column_count,
        coalesce(bool_and(
            attribute.atttypid = 'int4'::regtype
            AND NOT attribute.attnotnull
            AND NOT attribute.atthasdef
            AND attribute.attidentity = ''
            AND attribute.attgenerated = ''
        ), false) AS columns_valid
    FROM target_table
    LEFT JOIN pg_attribute AS attribute
      ON attribute.attrelid = target_table.table_oid
     AND attribute.attname IN ('promptCacheMissTokens', 'reasoningTokens')
     AND NOT attribute.attisdropped
), expected_constraints AS (
    SELECT
        constraint_definition.conname AS name,
        regexp_replace(
            pg_get_constraintdef(constraint_definition.oid),
            '\s+',
            '',
            'g'
        ) AS definition
    FROM pg_constraint AS constraint_definition
    WHERE constraint_definition.conrelid =
        'pg_temp.token_usage_details_constraint_contract'::regclass
      AND constraint_definition.contype = 'c'
), constraint_state AS (
    SELECT
        count(actual_constraint.oid) AS constraint_count,
        coalesce(bool_and(
            actual_constraint.convalidated
            AND regexp_replace(
                pg_get_constraintdef(actual_constraint.oid),
                '\s+',
                '',
                'g'
            ) = expected_constraints.definition
        ), false) AS constraints_valid
    FROM expected_constraints
    CROSS JOIN target_table
    LEFT JOIN pg_constraint AS actual_constraint
      ON actual_constraint.conrelid = target_table.table_oid
     AND actual_constraint.contype = 'c'
     AND actual_constraint.conname = expected_constraints.name
)
SELECT CASE
    WHEN target_table.table_oid IS NULL THEN 'partial'
    WHEN column_state.column_count = 0
     AND constraint_state.constraint_count = 0 THEN 'unmigrated'
    WHEN column_state.column_count = 2
     AND column_state.columns_valid
     AND constraint_state.constraint_count = 3
     AND constraint_state.constraints_valid THEN 'migrated'
    ELSE 'partial'
END
FROM target_table, column_state, constraint_state;
COMMIT;
SQL
  )" || { echo "schema-state:query-failed" >&2; exit 1; }
  case "$state" in
    unmigrated|migrated|partial) printf '%s\n' "$state" ;;
    *) echo "schema-state:invalid-result" >&2; exit 1 ;;
  esac
}

verify_sql_hash() {
  sql_path=$1
  expected_sha=$2
  printf '%s  %s\n' "$expected_sha" "$sql_path" | sha256sum --check --status -
}

case "$action" in
  status)
    query_schema_state
    ;;
  backup)
    [ "$(query_schema_state)" = "unmigrated" ] || {
      echo "生产备份只允许在完整未迁移状态执行" >&2
      exit 1
    }
    DATABASE_URL="$database_url"
    export DATABASE_URL
    backup_report="$(timeout 600 env \
      BACKUP_ROOT="$app_dir/.token-usage-production-backups" sh "$app_dir/scripts/backup.sh")"
    case "$backup_report" in
      备份完成：*) backup_dir="${backup_report#备份完成：}" ;;
      *) echo "无法定位生产备份目录" >&2; exit 1 ;;
    esac
    (
      cd -- "$backup_dir"
      sha256sum --check SHA256SUMS >/dev/null
    )
    timeout 180 pg_restore --list "$backup_dir/database.dump" >/dev/null
    printf 'backup-ok\n'
    ;;
  up)
    state="$(query_schema_state)"
    case "$state" in
      unmigrated|migrated) ;;
      partial) echo "schema-state:partial" >&2; exit 1 ;;
    esac
    verify_sql_hash "$forward_sql" "$forward_sha" || {
      echo "固定生产迁移 SQL 哈希不匹配" >&2
      exit 1
    }
    PGOPTIONS='-c statement_timeout=120000 -c lock_timeout=30000' \
      timeout 180 psql -v ON_ERROR_STOP=1 "$database_url" -f "$forward_sql" >/dev/null
    ;;
  down)
    state="$(query_schema_state)"
    case "$state" in
      unmigrated) exit 0 ;;
      migrated) ;;
      partial) echo "schema-state:partial" >&2; exit 1 ;;
    esac
    verify_sql_hash "$rollback_sql" "$rollback_sha" || {
      echo "固定生产回退 SQL 哈希不匹配" >&2
      exit 1
    }
    PGOPTIONS='-c statement_timeout=120000 -c lock_timeout=30000' \
      timeout 180 psql -v ON_ERROR_STOP=1 "$database_url" -f "$rollback_sql" >/dev/null
    [ "$(query_schema_state)" = "unmigrated" ] || {
      echo "生产回退后 schema 校验失败" >&2
      exit 1
    }
    ;;
esac
