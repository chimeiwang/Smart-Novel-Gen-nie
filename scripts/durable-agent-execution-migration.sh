#!/bin/sh
set -eu
umask 077

action="${1:-}"
target_database="${2:-}"
app_dir="${APP_DIR:-$(pwd)}"
env_file="${DURABLE_AGENT_MIGRATION_ENV_FILE:-$app_dir/.env}"
forward_sql="$app_dir/scripts/migrations/20260831_durable_agent_execution.sql"
rollback_sql="$app_dir/scripts/migrations/20260831_durable_agent_execution.rollback.sql"
backup_script="$app_dir/scripts/backup.sh"
compose_file="$app_dir/infra/compose.yaml"
forward_sha="f8342b40c63aba24075fba04a877a5601faa982ef7c40c99d8d164a80b502600"
rollback_sha="9855a0487d7c5f71723a2fdeda5ae81c3e10dcf0fbc0fa44cd9fceef30000db1"
pre_contract_sha="38878ffc1fde9f22b8790e0a5db40089d806e65cf82aacba1ec6fbabfb2ae1b2"
post_contract_sha="17af1745fb8e1addcf3e25e07a754f774c0e60f60c3603dd28acc841837e9e11"
pre_contract="$app_dir/apps/core-api-java/src/main/resources/db/pre-durable-agent-v2/schema-contract.json"
post_contract="$app_dir/apps/core-api-java/src/main/resources/db/post-durable-agent-v2/schema-contract.json"

case "$action" in
  status|active-v2-count|backup|forward|rollback) ;;
  *) echo "耐久 Agent 迁移动作必须是 status、active-v2-count、backup、forward 或 rollback" >&2; exit 2 ;;
esac
case "$target_database" in
  novelwriterdev|novelwriter) ;;
  *) echo "耐久 Agent 迁移目标必须精确指定 novelwriterdev 或 novelwriter" >&2; exit 2 ;;
esac

for command_name in python3 psql sha256sum timeout mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "耐久 Agent 迁移缺少必要命令：$command_name" >&2
    exit 1
  }
done
[ -r "$env_file" ] || { echo "迁移环境文件不可读" >&2; exit 1; }
[ -r "$forward_sql" ] || { echo "耐久 Agent forward SQL 不可读" >&2; exit 1; }
[ -r "$rollback_sql" ] || { echo "耐久 Agent rollback SQL 不可读" >&2; exit 1; }
[ -r "$pre_contract" ] || { echo "迁移前结构契约不可读" >&2; exit 1; }
[ -r "$post_contract" ] || { echo "迁移后结构契约不可读" >&2; exit 1; }

verify_fixed_file() {
  file_path=$1
  expected_sha=$2
  printf '%s  %s\n' "$expected_sha" "$file_path" | sha256sum --check --status -
}

verify_fixed_file "$forward_sql" "$forward_sha" || {
  echo "耐久 Agent forward SQL 哈希不匹配" >&2
  exit 1
}
verify_fixed_file "$rollback_sql" "$rollback_sha" || {
  echo "耐久 Agent rollback SQL 哈希不匹配" >&2
  exit 1
}
verify_fixed_file "$pre_contract" "$pre_contract_sha" || {
  echo "迁移前结构契约文件哈希不匹配" >&2
  exit 1
}
verify_fixed_file "$post_contract" "$post_contract_sha" || {
  echo "迁移后结构契约文件哈希不匹配" >&2
  exit 1
}

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/inkforge-durable-agent-migration.XXXXXX")"
case "$temp_dir" in
  "${TMPDIR:-/tmp}"/inkforge-durable-agent-migration.*) ;;
  *) echo "耐久 Agent 迁移临时目录不符合固定约定" >&2; exit 1 ;;
esac
pgpass_file="$temp_dir/pgpass"
operation_sql_file=""
cleanup() {
  rm -f -- "$pgpass_file"
  [ -z "$operation_sql_file" ] || rm -f -- "$operation_sql_file"
  rmdir -- "$temp_dir" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# 只从 .env 读取唯一 DATABASE_URL。密码仅写入 0600 PGPASSFILE；返回给 shell 的 URL 已移除密码。
set +x
database_url="$(python3 - "$env_file" "$pgpass_file" "$target_database" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

SAFE_QUERY_KEYS = {"application_name", "sslmode"}


class DatabaseUrlRejected(Exception):
    pass


def escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def parse_database_url(env_path: str, pgpass_path: str, target: str) -> str:
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
    normalized = matches[0]
    if normalized.startswith("postgresql+asyncpg://"):
        normalized = "postgresql://" + normalized[len("postgresql+asyncpg://") :]
    try:
        parts = urlsplit(normalized)
    except ValueError:
        raise DatabaseUrlRejected("url_split") from None
    if parts.scheme != "postgresql" or not parts.netloc:
        raise DatabaseUrlRejected("scheme_or_authority")
    if parts.path != f"/{target}":
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
        for item in (command_hostname, str(port), target, username, password)
    ) + "\n"
    descriptor = os.open(pgpass_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target_file:
        target_file.write(pgpass)

    safe_netloc = f"{quote(username, safe='')}@{command_hostname}"
    if parts.port is not None:
        safe_netloc += f":{parts.port}"
    return urlunsplit(parts._replace(netloc=safe_netloc))


try:
    print(parse_database_url(sys.argv[1], sys.argv[2], sys.argv[3]), end="")
except DatabaseUrlRejected as exc:
    print(f"database-url-check:{exc}", file=sys.stderr)
    raise SystemExit(1) from None
except (OSError, UnicodeError, ValueError):
    print("database-url-check:invalid", file=sys.stderr)
    raise SystemExit(1) from None
PY
)" || { echo "耐久 Agent DATABASE_URL 安全解析失败" >&2; exit 1; }
[ -s "$pgpass_file" ] || { echo "数据库凭据文件未生成" >&2; exit 1; }
chmod 600 "$pgpass_file"
PGPASSFILE="$pgpass_file"
export PGPASSFILE

query_schema_state() {
  structural_state="$(PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
WITH migration_shape AS (
  SELECT
    (
      SELECT count(*)
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
      WHERE namespace.nspname = 'public'
        AND relation.relkind = 'r'
        AND relation.relname = ANY (ARRAY[
          'WorkflowEvidenceBundle', 'WorkflowEvidenceItem', 'WorkflowEvent',
          'WorkflowEvaluation', 'WorkflowBillingReservation'
        ])
    ) AS new_table_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_attribute AS attribute
      WHERE attribute.attrelid = pg_catalog.to_regclass('public."WorkflowRun"')
        AND attribute.attname = ANY (ARRAY[
          'engineVersion', 'workflow', 'operation', 'operationCatalogVersion',
          'writingSessionId', 'parentRunId', 'idempotencyKey', 'requestHash',
          'targetType', 'targetId', 'budgetJson', 'modelPolicyJson',
          'currentEvidenceBundleId', 'lastEventSequence', 'revision',
          'cancelRequestId', 'cancelRequestedAt', 'completedAt', 'errorCode'
        ])
        AND attribute.attnum > 0
        AND NOT attribute.attisdropped
    ) AS run_column_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_attribute AS attribute
      WHERE attribute.attrelid = pg_catalog.to_regclass('public."WorkflowStep"')
        AND attribute.attname = ANY (ARRAY[
          'ordinal', 'purpose', 'lane', 'attemptCount', 'nextAttemptAt',
          'fencingToken', 'leaseExpiresAt', 'heartbeatAt', 'activeJobId',
          'idempotencyKey', 'requestHash', 'inputHash', 'resultHash',
          'evidenceBundleId', 'artifactId', 'artifactRevision', 'modelProfile',
          'modelProfileVersion', 'outputSchema', 'outputSchemaVersion',
          'budgetJson', 'resolvedModelJson', 'usageJson', 'lastProgressSequence',
          'cancelRequestId', 'submittedAt', 'updatedAt', 'completedAt', 'errorCode'
        ])
        AND attribute.attnum > 0
        AND NOT attribute.attisdropped
    ) AS step_column_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_constraint AS constraint_row
      WHERE constraint_row.conname = ANY (ARRAY[
        'WorkflowRun_v2_shape_check', 'WorkflowStep_v2_shape_check',
        'ReviewArtifact_workflow_owner_exclusive_check',
        'WorkflowEvidenceItem_existence_shape_check',
        'WorkflowBillingReservation_status_shape_check'
      ])
        AND constraint_row.convalidated
    ) AS key_constraint_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_class AS index_row
      JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = index_row.relnamespace
      WHERE namespace.nspname = 'public'
        AND index_row.relkind = 'i'
        AND index_row.relname = ANY (ARRAY[
          'WorkflowRun_v2_user_idempotency_key',
          'WorkflowRun_v2_writingSession_foreground_key',
          'WorkflowStep_run_ordinal_key',
          'WorkflowEvent_run_sequence_key',
          'WorkflowBillingReservation_stepId_key'
        ])
    ) AS key_index_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_trigger AS trigger_row
      WHERE trigger_row.tgname = ANY (ARRAY[
        'WorkflowBillingReservation_identity_immutable_trigger',
        'WorkflowRun_v2_identity_immutable_trigger',
        'WorkflowStep_v2_identity_immutable_trigger',
        'WorkflowEvidenceBundle_immutable_trigger',
        'WorkflowEvidenceItem_immutable_trigger',
        'WorkflowEvent_immutable_trigger',
        'WorkflowEvaluation_immutable_trigger'
      ])
        AND NOT trigger_row.tgisinternal
        AND trigger_row.tgenabled <> 'D'
    ) AS trigger_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_proc AS function_row
      JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = function_row.pronamespace
      WHERE namespace.nspname = 'public'
        AND function_row.proname = ANY (ARRAY[
          'rejectWorkflowAuditMutation', 'rejectWorkflowBillingIdentityMutation',
          'rejectWorkflowRunV2IdentityMutation', 'rejectWorkflowStepV2IdentityMutation'
        ])
    ) AS function_count,
    (
      SELECT count(*)
      FROM pg_catalog.pg_attribute AS attribute
      WHERE attribute.attrelid = pg_catalog.to_regclass('public."WorkflowRun"')
        AND attribute.attname = ANY (ARRAY['novelId', 'chapterId'])
        AND attribute.attnum > 0
        AND NOT attribute.attisdropped
        AND attribute.attnotnull
    ) AS run_scope_not_null_count
)
SELECT CASE
  WHEN pg_catalog.current_database() <> :'expected_database'
    THEN 'wrong-database'
  WHEN new_table_count = 0
    AND run_column_count = 0
    AND step_column_count = 0
    AND key_constraint_count = 0
    AND key_index_count = 0
    AND trigger_count = 0
    AND function_count = 0
    AND run_scope_not_null_count = 2
    THEN 'unmigrated'
  WHEN new_table_count = 5
    AND run_column_count = 19
    AND step_column_count = 29
    AND key_constraint_count = 5
    AND key_index_count = 5
    AND trigger_count = 7
    AND function_count = 4
    AND run_scope_not_null_count = 0
    THEN 'migrated'
  ELSE 'partial'
END
FROM migration_shape;
SQL
  )" || { echo "schema-state:query-failed" >&2; exit 1; }

  case "$structural_state" in
    unmigrated) printf '%s\n' unmigrated ;;
    partial) printf '%s\n' partial ;;
    migrated)
      v2_present="$(PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
        timeout 45 psql -X -v ON_ERROR_STOP=1 \
          -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
SELECT CASE WHEN
  pg_catalog.current_database() <> :'expected_database' THEN 'wrong-database'
  WHEN EXISTS (
    SELECT 1 FROM public."WorkflowRun"
    WHERE "novelId" IS NULL OR "chapterId" IS NULL
      OR "engineVersion" IS NOT NULL OR workflow IS NOT NULL OR operation IS NOT NULL
      OR "operationCatalogVersion" IS NOT NULL OR "writingSessionId" IS NOT NULL
      OR "parentRunId" IS NOT NULL OR "idempotencyKey" IS NOT NULL
      OR "requestHash" IS NOT NULL OR "targetType" IS NOT NULL
      OR "targetId" IS NOT NULL OR "budgetJson" IS NOT NULL
      OR "modelPolicyJson" IS NOT NULL OR "currentEvidenceBundleId" IS NOT NULL
      OR "lastEventSequence" IS NOT NULL OR revision IS NOT NULL
      OR "cancelRequestId" IS NOT NULL OR "cancelRequestedAt" IS NOT NULL
      OR "completedAt" IS NOT NULL OR "errorCode" IS NOT NULL
  )
  OR EXISTS (
    SELECT 1 FROM public."WorkflowStep"
    WHERE ordinal IS NOT NULL OR purpose IS NOT NULL OR lane IS NOT NULL
      OR "attemptCount" IS NOT NULL OR "nextAttemptAt" IS NOT NULL
      OR "fencingToken" IS NOT NULL OR "leaseExpiresAt" IS NOT NULL
      OR "heartbeatAt" IS NOT NULL OR "activeJobId" IS NOT NULL
      OR "idempotencyKey" IS NOT NULL OR "requestHash" IS NOT NULL
      OR "inputHash" IS NOT NULL OR "resultHash" IS NOT NULL
      OR "evidenceBundleId" IS NOT NULL OR "artifactId" IS NOT NULL
      OR "artifactRevision" IS NOT NULL OR "modelProfile" IS NOT NULL
      OR "modelProfileVersion" IS NOT NULL OR "outputSchema" IS NOT NULL
      OR "outputSchemaVersion" IS NOT NULL OR "budgetJson" IS NOT NULL
      OR "resolvedModelJson" IS NOT NULL OR "usageJson" IS NOT NULL
      OR "lastProgressSequence" IS NOT NULL OR "cancelRequestId" IS NOT NULL
      OR "submittedAt" IS NOT NULL OR "updatedAt" IS NOT NULL
      OR "completedAt" IS NOT NULL OR "errorCode" IS NOT NULL
  )
  OR EXISTS (SELECT 1 FROM public."WorkflowEvidenceBundle")
  OR EXISTS (SELECT 1 FROM public."WorkflowEvidenceItem")
  OR EXISTS (SELECT 1 FROM public."WorkflowEvent")
  OR EXISTS (SELECT 1 FROM public."WorkflowEvaluation")
  OR EXISTS (SELECT 1 FROM public."WorkflowBillingReservation")
  OR EXISTS (SELECT 1 FROM public."ReviewArtifact" WHERE "workflowRunId" IS NOT NULL)
THEN 'with-v2' ELSE 'empty-v2' END;
SQL
      )" || { echo "v2-data-state:query-failed" >&2; exit 1; }
      case "$v2_present" in
        empty-v2) printf '%s\n' migrated-empty-v2 ;;
        with-v2) printf '%s\n' migrated-with-v2 ;;
        wrong-database) echo "v2-data-state:wrong-database" >&2; exit 1 ;;
        *) echo "v2-data-state:invalid-result" >&2; exit 1 ;;
      esac
      ;;
    wrong-database) echo "schema-state:wrong-database" >&2; exit 1 ;;
    *) echo "schema-state:invalid-result" >&2; exit 1 ;;
  esac
}

query_active_v2_run_count() {
  current_state="$(query_schema_state)"
  case "$current_state" in
    migrated-empty-v2|migrated-with-v2) ;;
    unmigrated)
      echo "active-v2-count:requires-migrated-schema" >&2
      exit 1
      ;;
    partial)
      echo "active-v2-count:partial-schema" >&2
      exit 1
      ;;
    *)
      echo "active-v2-count:invalid-schema-state" >&2
      exit 1
      ;;
  esac

  active_count="$(PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
SELECT CASE
  WHEN pg_catalog.current_database() <> :'expected_database' THEN 'wrong-database'
  ELSE (
    SELECT count(*)::text
    FROM public."WorkflowRun"
    WHERE "engineVersion" = 2
      AND (
        status IS NULL
        OR status::text NOT IN ('completed', 'failed', 'cancelled')
      )
  )
END;
SQL
  )" || { echo "active-v2-count:query-failed" >&2; exit 1; }

  case "$active_count" in
    wrong-database)
      echo "active-v2-count:wrong-database" >&2
      exit 1
      ;;
    ""|*[!0-9]*)
      echo "active-v2-count:invalid-result" >&2
      exit 1
      ;;
  esac
  printf '%s\n' "$active_count"
}

read_rollout_config() {
  python3 - "$env_file" <<'PY'
import sys
from pathlib import Path

allowed = {
    "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
    "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
    "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST",
    "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST",
}
values: dict[str, str] = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in allowed:
        continue
    if key in values:
        print("rollout-config:duplicate", file=sys.stderr)
        raise SystemExit(1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    values[key] = value

schema_ready = values.get("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "false").lower()
route_mode = values.get("DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off").lower()
if schema_ready not in {"true", "false"} or route_mode not in {
    "off", "allowlist", "all"
}:
    print("rollout-config:invalid", file=sys.stderr)
    raise SystemExit(1)
print(schema_ready)
print(route_mode)
print("present" if values.get("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", "").strip() else "absent")
print("present" if values.get("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", "").strip() else "absent")
PY
}

require_pre_migration_route_off() {
  config="$(read_rollout_config)" || { echo "耐久 Agent 发布配置无法安全解析" >&2; exit 1; }
  schema_ready="$(printf '%s\n' "$config" | sed -n '1p')"
  route_mode="$(printf '%s\n' "$config" | sed -n '2p')"
  [ "$schema_ready" = "false" ] && [ "$route_mode" = "off" ] || {
    echo "DDL 操作要求 schemaReady=false 且 V2 route=off" >&2
    exit 1
  }
}

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

require_compatible_core_and_exact_contract() {
  command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; exit 1; }
  [ -r "$compose_file" ] || { echo "生产 Compose 文件不可读" >&2; exit 1; }
  # 两个资源名与 V2 装配闸门必须真实存在于当前运行 JAR；只靠 Java runtime 标签不足以证明兼容。
  compose exec -T core-api /bin/sh -ec \
    "grep -aFq 'pre-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
     grep -aFq 'post-durable-agent-v2/schema-contract.json' /app/inkforge-core-api.jar && \
     grep -aFq 'DurableAgentSchemaGate.class' /app/inkforge-core-api.jar" >/dev/null
  compose exec -T core-api /usr/local/bin/inkforge-schema-guard >/dev/null
}

require_production_confirmation() {
  confirmation_action=$1
  confirmation_file="${DURABLE_AGENT_MIGRATION_CONFIRM_FILE:-}"
  [ -n "$confirmation_file" ] || { echo "正式库 DDL 缺少确认令牌文件" >&2; exit 1; }
  python3 - "$confirmation_file" "$target_database" "$confirmation_action" <<'PY'
import os
import stat
import sys
from pathlib import Path

if sys.argv[2] != "novelwriter" or sys.argv[3] not in {"apply", "rollback-empty-v2"}:
    print("production-confirmation-context:invalid", file=sys.stderr)
    raise SystemExit(1)
expected = f"{sys.argv[2]}:20260831:{sys.argv[3]}"
path = Path(sys.argv[1])
try:
    metadata = path.stat()
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError
    value = path.read_text(encoding="utf-8")
except (OSError, UnicodeError, ValueError):
    print("production-confirmation-file:invalid", file=sys.stderr)
    raise SystemExit(1) from None
if value.endswith("\n"):
    value = value[:-1]
if "\n" in value or "\r" in value or value != expected:
    print("production-confirmation-token:mismatch", file=sys.stderr)
    raise SystemExit(1)
PY
}

resolve_execution_redis_container() {
  explicit="${EXECUTION_REDIS_CONTAINER:-}"
  if [ -n "$explicit" ]; then
    case "$explicit" in
      *[!A-Za-z0-9_.-]*|'') echo "execution Redis 容器身份无效" >&2; exit 1 ;;
    esac
    printf '%s\n' "$explicit"
    return
  fi
  container_id="$(compose ps -q execution-redis)"
  case "$container_id" in
    *[!A-Za-z0-9]*|'') echo "无法唯一解析 execution Redis 容器" >&2; exit 1 ;;
  esac
  printf '%s\n' "$container_id"
}

verify_backup_dir() {
  backup_dir="${DURABLE_AGENT_MIGRATION_BACKUP_DIR:-}"
  [ -n "$backup_dir" ] || { echo "forward/rollback 必须显式指定已验证备份目录" >&2; exit 1; }
  [ -d "$backup_dir" ] && [ ! -L "$backup_dir" ] \
    && [ -r "$backup_dir/SHA256SUMS" ] && [ ! -L "$backup_dir/SHA256SUMS" ] || {
    echo "耐久 Agent 迁移备份目录无效" >&2
    exit 1
  }
  python3 - "$backup_dir/SHA256SUMS" <<'PY'
import re
import sys
from pathlib import Path

allowed = {
    "database.dump",
    "recovery-boundary.meta",
    "uploads.tar.gz",
    "execution-journal.rdb",
    "execution-journal.meta",
    "durable-agent-migration.meta",
}
required = allowed - {"uploads.tar.gz"}
names: list[str] = []
try:
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None:
            raise ValueError
        names.append(match.group(2))
except (OSError, UnicodeError, ValueError):
    print("backup-checksums:invalid", file=sys.stderr)
    raise SystemExit(1) from None
if len(names) != len(set(names)) or not required.issubset(names) or not set(names) <= allowed:
    print("backup-checksums:unexpected-files", file=sys.stderr)
    raise SystemExit(1)
PY
  (
    cd -- "$backup_dir"
    sha256sum --check SHA256SUMS >/dev/null
  ) || { echo "耐久 Agent 迁移备份校验和失败" >&2; exit 1; }
  timeout 180 pg_restore --list "$backup_dir/database.dump" >/dev/null || {
    echo "PostgreSQL 备份归档不可读" >&2
    exit 1
  }
  for required_file in \
    recovery-boundary.meta execution-journal.rdb execution-journal.meta \
    durable-agent-migration.meta
  do
    [ -s "$backup_dir/$required_file" ] && [ ! -L "$backup_dir/$required_file" ] || {
      echo "耐久 Agent 迁移备份缺少 execution journal 或恢复边界" >&2
      exit 1
    }
  done
  grep -qx 'postgresRestoreRequiresExecutionQuarantine=true' \
    "$backup_dir/recovery-boundary.meta" || {
      echo "PostgreSQL 备份缺少 restore quarantine 边界" >&2
      exit 1
    }
  grep -qx 'executionJournalIncluded=true' \
    "$backup_dir/recovery-boundary.meta" || {
      echo "耐久 Agent 迁移备份没有纳入 execution journal" >&2
      exit 1
    }
  grep -qx 'restoreRequiresNamedReconciliation=true' \
    "$backup_dir/execution-journal.meta" || {
      echo "execution journal 备份缺少具名对账边界" >&2
      exit 1
    }
  grep -qx "database=$target_database" "$backup_dir/durable-agent-migration.meta" || {
    echo "备份数据库身份与当前目标不一致" >&2
    exit 1
  }
  grep -qx 'schemaState=unmigrated' "$backup_dir/durable-agent-migration.meta" || {
    echo "备份不是从完整迁移前结构取得" >&2
    exit 1
  }
  grep -qx "forwardSha256=$forward_sha" "$backup_dir/durable-agent-migration.meta" || {
    echo "备份绑定的 forward SQL 与当前文件不一致" >&2
    exit 1
  }
  grep -qx "rollbackSha256=$rollback_sha" "$backup_dir/durable-agent-migration.meta" || {
    echo "备份绑定的 rollback SQL 与当前文件不一致" >&2
    exit 1
  }
}

apply_sql() {
  sql_path=$1
  production_token=$2
  pg_options='-c statement_timeout=180000 -c lock_timeout=30000'
  execution_sql="$sql_path"
  if [ "$target_database" = "novelwriter" ]; then
    # 生产 GUC 只进入 0600 临时 SQL，不进入 psql argv 或子进程环境。
    operation_sql_file="$temp_dir/$(basename -- "$sql_path")"
    {
      printf "SET inkforge.durable_agent_execution_production = '%s';\n" \
        "$production_token"
      cat "$sql_path"
    } > "$operation_sql_file"
    chmod 600 "$operation_sql_file"
    execution_sql="$operation_sql_file"
  fi
  PGOPTIONS="$pg_options" timeout 240 psql -X -v ON_ERROR_STOP=1 \
    "$database_url" -f "$execution_sql" >/dev/null
}

case "$action" in
  status)
    query_schema_state
    ;;
  active-v2-count)
    query_active_v2_run_count
    ;;
  backup)
    command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
    command -v pg_dump >/dev/null 2>&1 || { echo "缺少 pg_dump" >&2; exit 1; }
    command -v pg_restore >/dev/null 2>&1 || { echo "缺少 pg_restore" >&2; exit 1; }
    [ -r "$backup_script" ] || { echo "备份脚本不可读" >&2; exit 1; }
    require_pre_migration_route_off
    [ "$(query_schema_state)" = "unmigrated" ] || {
      echo "耐久 Agent 迁移备份只允许从完整迁移前结构创建" >&2
      exit 1
    }
    require_compatible_core_and_exact_contract
    execution_container="$(resolve_execution_redis_container)"
    backup_report="$(timeout 900 env \
      DATABASE_URL="$database_url" \
      PGPASSFILE="$pgpass_file" \
      BACKUP_ROOT="${DURABLE_AGENT_MIGRATION_BACKUP_ROOT:-$app_dir/.durable-agent-execution-backups/$target_database}" \
      EXECUTION_REDIS_CONTAINER="$execution_container" \
      sh "$backup_script")"
    case "$backup_report" in
      备份完成：*) backup_dir="${backup_report#备份完成：}" ;;
      *) echo "无法定位耐久 Agent 迁移备份目录" >&2; exit 1 ;;
    esac
    {
      printf 'format=inkforge-durable-agent-migration-backup/1\n'
      printf 'database=%s\n' "$target_database"
      printf 'schemaState=unmigrated\n'
      printf 'forwardSha256=%s\n' "$forward_sha"
      printf 'rollbackSha256=%s\n' "$rollback_sha"
      printf 'preContractFileSha256=%s\n' "$pre_contract_sha"
      printf 'postContractFileSha256=%s\n' "$post_contract_sha"
      printf 'executionJournalRequired=true\n'
    } > "$backup_dir/durable-agent-migration.meta"
    (
      cd -- "$backup_dir"
      sha256sum durable-agent-migration.meta >> SHA256SUMS
    )
    DURABLE_AGENT_MIGRATION_BACKUP_DIR="$backup_dir"
    export DURABLE_AGENT_MIGRATION_BACKUP_DIR
    verify_backup_dir
    printf 'backup-ok:%s\n' "$backup_dir"
    ;;
  forward)
    command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
    command -v pg_restore >/dev/null 2>&1 || { echo "缺少 pg_restore" >&2; exit 1; }
    require_pre_migration_route_off
    current_state="$(query_schema_state)"
    case "$current_state" in
      unmigrated|migrated-empty-v2) ;;
      migrated-with-v2) echo "已有 V2 数据，拒绝把 forward 当作普通重放" >&2; exit 1 ;;
      partial) echo "schema-state:partial" >&2; exit 1 ;;
      *) echo "schema-state:invalid-result" >&2; exit 1 ;;
    esac
    verify_backup_dir
    require_compatible_core_and_exact_contract
    if [ "$target_database" = "novelwriter" ]; then
      require_production_confirmation apply
    fi
    apply_sql "$forward_sql" 'novelwriter:20260831:apply'
    [ "$(query_schema_state)" = "migrated-empty-v2" ] || {
      echo "耐久 Agent forward 后没有达到完整空 V2 结构" >&2
      exit 1
    }
    require_compatible_core_and_exact_contract
    printf 'forward-ok\n'
    ;;
  rollback)
    command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
    command -v pg_restore >/dev/null 2>&1 || { echo "缺少 pg_restore" >&2; exit 1; }
    require_pre_migration_route_off
    current_state="$(query_schema_state)"
    case "$current_state" in
      unmigrated) printf 'rollback-ok\n'; exit 0 ;;
      migrated-empty-v2) ;;
      migrated-with-v2)
        echo "检测到 V2 数据，DDL rollback 永久禁止；只能使用 V2-aware route-off 镜像排空" >&2
        exit 1
        ;;
      partial) echo "schema-state:partial" >&2; exit 1 ;;
      *) echo "schema-state:invalid-result" >&2; exit 1 ;;
    esac
    verify_backup_dir
    require_compatible_core_and_exact_contract
    if [ "$target_database" = "novelwriter" ]; then
      require_production_confirmation rollback-empty-v2
    fi
    apply_sql "$rollback_sql" 'novelwriter:20260831:rollback-empty-v2'
    [ "$(query_schema_state)" = "unmigrated" ] || {
      echo "耐久 Agent rollback 后没有恢复完整迁移前结构" >&2
      exit 1
    }
    require_compatible_core_and_exact_contract
    printf 'rollback-ok\n'
    ;;
esac
