#!/bin/sh
set -eu
umask 077
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

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
contract_evidence_builder="$app_dir/scripts/durable_agent_contract_evidence.py"
joint_drain_builder="$app_dir/scripts/durable_agent_joint_drain.py"
boundary_builder="$app_dir/scripts/durable_agent_release_boundary.py"
v1_queue_snapshot_lua="$app_dir/scripts/durable_agent_v1_queue_snapshot.lua"
v2_execution_snapshot_lua="$app_dir/scripts/durable_agent_v2_execution_snapshot.lua"
v1_pre_activation_snapshot_lua="$app_dir/scripts/durable_agent_v1_pre_activation_snapshot.lua"
v2_pre_activation_snapshot_lua="$app_dir/scripts/durable_agent_v2_pre_activation_snapshot.lua"
v1_drain_index_initialize_lua="$app_dir/scripts/durable_agent_v1_drain_index_initialize.lua"
v2_drain_index_initialize_lua="$app_dir/scripts/durable_agent_v2_drain_index_initialize.lua"

case "$action" in
  status|active-v2-count|initialize-drain-indexes|drain-status|verify-drain|boundary-drain|backup|forward|rollback|export-contract|verify-contract) ;;
  *) echo "耐久 Agent 迁移动作无效" >&2; exit 2 ;;
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
[ -r "$contract_evidence_builder" ] || { echo "迁移后结构证据构建器不可读" >&2; exit 1; }

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
contract_evidence_temp_dir=""
cleanup() {
  cleanup_status="${1:-0}"
  rm -f -- "$pgpass_file"
  rm -f -- \
    "$temp_dir/source.json" "$temp_dir/schema-only.current.sql" \
    "$temp_dir/drain-runtime-before.json" "$temp_dir/drain-postgres-before.json" \
    "$temp_dir/drain-v1-redis.json" "$temp_dir/drain-v2-redis.json" \
    "$temp_dir/drain-postgres-after.json" "$temp_dir/drain-runtime-after.json" \
    "$temp_dir/drain-report.json" "$temp_dir/boundary-runtime-before.json" \
    "$temp_dir/boundary-runtime-after.json" \
    "$temp_dir/boundary-postgres-before.json" \
    "$temp_dir/boundary-postgres-after.json" \
    "$temp_dir/boundary-v1-redis.json" "$temp_dir/boundary-v2-redis.json" \
    "$temp_dir/boundary-joint-report.json"
  [ -z "$operation_sql_file" ] || rm -f -- "$operation_sql_file"
  if [ -n "$contract_evidence_temp_dir" ]; then
    rm -f -- \
      "$contract_evidence_temp_dir/schema-contract.json" \
      "$contract_evidence_temp_dir/schema-only.sql" \
      "$contract_evidence_temp_dir/contract-verification.meta" \
      "$contract_evidence_temp_dir/SHA256SUMS" \
      "$contract_evidence_temp_dir/source.json" \
      "$contract_evidence_temp_dir/schema-only.current.sql"
    rmdir -- "$contract_evidence_temp_dir" 2>/dev/null || true
  fi
  rmdir -- "$temp_dir" 2>/dev/null || true
  return "$cleanup_status"
}
trap 'cleanup_status=$?; trap - EXIT; cleanup "$cleanup_status"; exit "$cleanup_status"' EXIT
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

query_joint_drain_postgres() {
  PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL TIME ZONE 'UTC';
WITH
observed AS MATERIALIZED (
  SELECT pg_catalog.clock_timestamp() AT TIME ZONE 'UTC' AS value
),
metric_names(name) AS (VALUES
  ('v1WritingTasksActive'),
  ('v1WritingTasksAwaitingUser'),
  ('v1WritingTasksRecoverable'),
  ('v1CommandsActive'),
  ('v1OutboxUndelivered'),
  ('v1ArtifactsAwaitingUser'),
  ('v1ArtifactsRecoverable'),
  ('v2RunsActive'),
  ('v2StepsActive'),
  ('v2BillingReserved'),
  ('v2BillingReconciliationRequired')
),
blockers(metric, id, "createdAt") AS (
  SELECT 'v1WritingTasksActive', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text IN ('idle', 'active', 'waiting_call')
  UNION ALL
  SELECT 'v1WritingTasksAwaitingUser', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text = 'awaiting_user_review'
  UNION ALL
  SELECT 'v1WritingTasksRecoverable', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text IN ('active', 'waiting_call') AND "graphStateJson" IS NOT NULL
  UNION ALL
  SELECT 'v1CommandsActive', id, "createdAt"
  FROM public."WritingRunCommand"
  WHERE status IN ('pending', 'submitted', 'processing')
  UNION ALL
  SELECT 'v1OutboxUndelivered', id, "createdAt"
  FROM public."WritingEventOutbox"
  WHERE "deliveryState" IN ('pending', 'delivering', 'blocked')
  UNION ALL
  SELECT 'v1ArtifactsAwaitingUser', id, "createdAt"
  FROM public."ReviewArtifact"
  WHERE "taskId" IS NOT NULL AND "workflowRunId" IS NULL
    AND status::text = 'awaiting_user'
  UNION ALL
  SELECT 'v1ArtifactsRecoverable', id, "createdAt"
  FROM public."ReviewArtifact"
  WHERE "taskId" IS NOT NULL AND "workflowRunId" IS NULL
    AND status::text IN ('draft', 'under_review', 'applying')
  UNION ALL
  SELECT 'v2RunsActive', id, "createdAt"
  FROM public."WorkflowRun"
  WHERE "engineVersion" = 2
    AND (status IS NULL OR status::text NOT IN ('completed', 'failed', 'cancelled'))
  UNION ALL
  SELECT 'v2StepsActive', step.id, step."createdAt"
  FROM public."WorkflowStep" AS step
  JOIN public."WorkflowRun" AS run ON run.id = step."runId"
  WHERE run."engineVersion" = 2 AND step.status::text IN ('pending', 'running')
  UNION ALL
  SELECT 'v2BillingReserved', id, "createdAt"
  FROM public."WorkflowBillingReservation"
  WHERE status = 'reserved'
  UNION ALL
  SELECT 'v2BillingReconciliationRequired', id, "createdAt"
  FROM public."WorkflowBillingReservation"
  WHERE status = 'reconciliation_required'
),
metric_json AS (
  SELECT names.name, COALESCE((
    SELECT pg_catalog.json_agg(
      pg_catalog.json_build_object(
        'id', blocker.id,
        'at', to_char(blocker."createdAt", 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
      ) ORDER BY blocker."createdAt", blocker.id
    )
    FROM blockers AS blocker
    WHERE blocker.metric = names.name
  ), '[]'::json) AS entries
  FROM metric_names AS names
)
SELECT pg_catalog.json_build_object(
  'sourceVersion', '2',
  'database', pg_catalog.current_database(),
  'identity', pg_catalog.json_build_object(
    'databaseOid', (
      SELECT oid::bigint FROM pg_catalog.pg_database
      WHERE datname = pg_catalog.current_database()
    ),
    'serverAddress', COALESCE(pg_catalog.inet_server_addr()::text, 'local'),
    'serverPort', COALESCE(pg_catalog.inet_server_port(), 0),
    'serverVersionNum', pg_catalog.current_setting('server_version_num')::integer
  ),
  'observedAt', (
    SELECT to_char(value, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') FROM observed
  ),
  'snapshot', pg_catalog.pg_current_snapshot()::text,
  'walLsn', pg_catalog.pg_current_wal_lsn()::text,
  'metrics', (SELECT pg_catalog.json_object_agg(name, entries) FROM metric_json)
)
FROM observed
WHERE pg_catalog.current_database() = :'expected_database';
COMMIT;
SQL
}

query_pre_contract_drain_postgres() {
  PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL TIME ZONE 'UTC';
WITH
observed AS MATERIALIZED (
  SELECT pg_catalog.clock_timestamp() AT TIME ZONE 'UTC' AS value
),
metric_names(name) AS (VALUES
  ('v1WritingTasksActive'),
  ('v1WritingTasksAwaitingUser'),
  ('v1WritingTasksRecoverable'),
  ('v1CommandsActive'),
  ('v1OutboxUndelivered'),
  ('v1ArtifactsAwaitingUser'),
  ('v1ArtifactsRecoverable')
),
blockers(metric, id, "createdAt") AS (
  SELECT 'v1WritingTasksActive', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text IN ('idle', 'active', 'waiting_call')
  UNION ALL
  SELECT 'v1WritingTasksAwaitingUser', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text = 'awaiting_user_review'
  UNION ALL
  SELECT 'v1WritingTasksRecoverable', id, "createdAt"
  FROM public."WritingTask"
  WHERE phase::text IN ('active', 'waiting_call') AND "graphStateJson" IS NOT NULL
  UNION ALL
  SELECT 'v1CommandsActive', id, "createdAt"
  FROM public."WritingRunCommand"
  WHERE status IN ('pending', 'submitted', 'processing')
  UNION ALL
  SELECT 'v1OutboxUndelivered', id, "createdAt"
  FROM public."WritingEventOutbox"
  WHERE "deliveryState" IN ('pending', 'delivering', 'blocked')
  UNION ALL
  SELECT 'v1ArtifactsAwaitingUser', id, "createdAt"
  FROM public."ReviewArtifact"
  WHERE "taskId" IS NOT NULL AND "workflowRunId" IS NULL
    AND status::text = 'awaiting_user'
  UNION ALL
  SELECT 'v1ArtifactsRecoverable', id, "createdAt"
  FROM public."ReviewArtifact"
  WHERE "taskId" IS NOT NULL AND "workflowRunId" IS NULL
    AND status::text IN ('draft', 'under_review', 'applying')
),
metric_json AS (
  SELECT names.name, COALESCE((
    SELECT pg_catalog.json_agg(
      pg_catalog.json_build_object(
        'id', blocker.id,
        'at', to_char(blocker."createdAt", 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
      ) ORDER BY blocker."createdAt", blocker.id
    )
    FROM blockers AS blocker
    WHERE blocker.metric = names.name
  ), '[]'::json) AS entries
  FROM metric_names AS names
)
SELECT pg_catalog.json_build_object(
  'sourceVersion', '2',
  'database', pg_catalog.current_database(),
  'identity', pg_catalog.json_build_object(
    'databaseOid', (
      SELECT oid::bigint FROM pg_catalog.pg_database
      WHERE datname = pg_catalog.current_database()
    ),
    'serverAddress', COALESCE(pg_catalog.inet_server_addr()::text, 'local'),
    'serverPort', COALESCE(pg_catalog.inet_server_port(), 0),
    'serverVersionNum', pg_catalog.current_setting('server_version_num')::integer
  ),
  'observedAt', (
    SELECT to_char(value, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') FROM observed
  ),
  'snapshot', pg_catalog.pg_current_snapshot()::text,
  'walLsn', pg_catalog.pg_current_wal_lsn()::text,
  'metrics', (SELECT pg_catalog.json_object_agg(name, entries) FROM metric_json)
)
FROM observed
WHERE pg_catalog.current_database() = :'expected_database';
COMMIT;
SQL
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

require_joint_drain_assets() {
  [ -r "$joint_drain_builder" ] || { echo "联合 drain 状态构建器不可读" >&2; exit 1; }
  [ -r "$v1_queue_snapshot_lua" ] || { echo "V1 普通 Redis drain 快照不可读" >&2; exit 1; }
  [ -r "$v2_execution_snapshot_lua" ] || { echo "V2 execution Redis drain 快照不可读" >&2; exit 1; }
  [ -r "$v1_drain_index_initialize_lua" ] || { echo "V1 drain 索引初始化脚本不可读" >&2; exit 1; }
  [ -r "$v2_drain_index_initialize_lua" ] || { echo "V2 drain 索引初始化脚本不可读" >&2; exit 1; }
}

require_boundary_drain_assets() {
  require_joint_drain_assets
  [ -r "$boundary_builder" ] || { echo "boundary drain 构建器不可读" >&2; exit 1; }
  [ -r "$v1_pre_activation_snapshot_lua" ] || {
    echo "V1 pre-activation Redis 快照不可读" >&2
    exit 1
  }
  [ -r "$v2_pre_activation_snapshot_lua" ] || {
    echo "V2 pre-activation Redis 快照不可读" >&2
    exit 1
  }
}

resolve_compose_container_identity() {
  service=$1
  container_id="$(compose ps -q "$service")" || return 1
  case "$container_id" in
    ''|*[!0-9a-f]*) echo "无法唯一解析 $service 容器" >&2; return 1 ;;
  esac
  [ "${#container_id}" -ge 12 ] && [ "${#container_id}" -le 64 ] || {
    echo "$service 容器 ID 格式无效" >&2
    return 1
  }
  image_id="$(docker inspect --format '{{.Image}}' "$container_id")" || return 1
  case "$image_id" in
    sha256:[0-9a-f]*) ;;
    *) echo "$service 镜像 ID 格式无效" >&2; return 1 ;;
  esac
  [ "${#image_id}" -eq 71 ] || { echo "$service 镜像 ID 长度无效" >&2; return 1; }
  printf '%s\n%s\n' "$container_id" "$image_id"
}

read_redis_run_id() {
  service=$1
  run_id="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T "$service" redis-cli --raw INFO server \
    | tr -d '\r' | sed -n 's/^run_id:\([0-9a-f][0-9a-f]*\)$/\1/p')" || return 1
  case "$run_id" in
    *[!0-9a-f]*|'') echo "$service Redis run_id 无效" >&2; return 1 ;;
  esac
  [ "${#run_id}" -eq 40 ] || { echo "$service Redis run_id 长度无效" >&2; return 1; }
  printf '%s\n' "$run_id"
}

read_running_core_drain_config() {
  timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T core-api /bin/sh -ec '
    grep -aFq "V1FreshAgentStartGate.class" /app/inkforge-core-api.jar
    grep -aFq "V1_FRESH_AGENT_STARTS_ENABLED" /app/inkforge-core-api.jar
    normalize_bool() {
      value=$(printf "%s" "$1" | tr "[:upper:]" "[:lower:]")
      case "$value" in
        true|1) printf "true\n" ;;
        false|0) printf "false\n" ;;
        *) exit 41 ;;
      esac
    }
    normalize_route() {
      value=$(printf "%s" "$1" | tr "[:upper:]" "[:lower:]")
      case "$value" in off|allowlist|all) printf "%s\n" "$value" ;; *) exit 42 ;; esac
    }
    normalize_bool "${DURABLE_AGENT_EXECUTION_SCHEMA_READY:-false}"
    normalize_route "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-off}"
    normalize_bool "${V1_FRESH_AGENT_STARTS_ENABLED:-true}"
  '
}

write_runtime_topology() {
  output_path=$1
  core_identity="$(resolve_compose_container_identity core-api)" || return 1
  redis_identity="$(resolve_compose_container_identity redis)" || return 1
  execution_identity="$(resolve_compose_container_identity execution-redis)" || return 1
  core_config="$(read_running_core_drain_config)" || {
    echo "运行 Core 未包含可证明的联合 drain 门禁" >&2
    return 1
  }
  ordinary_run_id="$(read_redis_run_id redis)" || return 1
  execution_run_id="$(read_redis_run_id execution-redis)" || return 1
  python3 - "$output_path" \
    "$(printf '%s\n' "$core_identity" | sed -n '1p')" \
    "$(printf '%s\n' "$core_identity" | sed -n '2p')" \
    "$(printf '%s\n' "$core_config" | sed -n '1p')" \
    "$(printf '%s\n' "$core_config" | sed -n '2p')" \
    "$(printf '%s\n' "$core_config" | sed -n '3p')" \
    "$(printf '%s\n' "$redis_identity" | sed -n '1p')" \
    "$(printf '%s\n' "$redis_identity" | sed -n '2p')" "$ordinary_run_id" \
    "$(printf '%s\n' "$execution_identity" | sed -n '1p')" \
    "$(printf '%s\n' "$execution_identity" | sed -n '2p')" "$execution_run_id" <<'PY'
import json
import os
import sys

path = sys.argv[1]
value = {
    "sourceVersion": "1",
    "core": {
        "containerId": sys.argv[2],
        "imageId": sys.argv[3],
        "schemaReady": sys.argv[4] == "true",
        "routeMode": sys.argv[5],
        "v1FreshStartsEnabled": sys.argv[6] == "true",
    },
    "redis": {
        "containerId": sys.argv[7],
        "imageId": sys.argv[8],
        "redisRunId": sys.argv[9],
    },
    "executionRedis": {
        "containerId": sys.argv[10],
        "imageId": sys.argv[11],
        "redisRunId": sys.argv[12],
    },
}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
    json.dump(value, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
}

read_joint_drain_redis() {
  redis_service=$1
  lua_path=$2
  output_path=$3
  lua_source="$(cat "$lua_path")" || {
    echo "联合 drain Redis Lua 无法读取" >&2
    return 1
  }
  timeout 20 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T "$redis_service" redis-cli --raw EVAL_RO "$lua_source" 0 \
    > "$output_path" || {
      echo "联合 drain 无法读取 $redis_service" >&2
      return 1
    }
  [ -s "$output_path" ] || {
    echo "联合 drain 的 $redis_service 返回空快照" >&2
    return 1
  }
}

require_joint_drain_redis_health() {
  ordinary_ping="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T redis redis-cli --raw PING | tr -d '\r')" || {
      echo "联合 drain 无法连接普通 Redis" >&2
      exit 1
    }
  [ "$ordinary_ping" = "PONG" ] || { echo "普通 Redis PING 无效" >&2; exit 1; }

  execution_persistence="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T execution-redis redis-cli --raw INFO persistence | tr -d '\r')" || {
      echo "联合 drain 无法读取 execution Redis AOF 状态" >&2
      exit 1
    }
  printf '%s\n' "$execution_persistence" | grep -q '^aof_enabled:1$' || {
    echo "联合 drain 要求 execution Redis 启用 AOF" >&2
    exit 1
  }
  printf '%s\n' "$execution_persistence" | grep -q '^aof_last_write_status:ok$' || {
    echo "联合 drain 检测到 execution Redis AOF 写入异常" >&2
    exit 1
  }
  execution_evicted="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T execution-redis redis-cli --raw INFO stats | tr -d '\r' \
    | sed -n 's/^evicted_keys:\([0-9][0-9]*\)$/\1/p')" || {
      echo "联合 drain 无法读取 execution Redis eviction" >&2
      exit 1
    }
  [ "$execution_evicted" = "0" ] || {
    echo "联合 drain 检测到 execution Redis eviction 或无效统计" >&2
    exit 1
  }
}

query_all_v2_run_count() {
  result="$(PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT CASE
  WHEN pg_catalog.current_database() <> :'expected_database' THEN 'wrong-database'
  ELSE (SELECT count(*)::text FROM public."WorkflowRun" WHERE "engineVersion" = 2)
END;
COMMIT;
SQL
  )" || { echo "全部 V2 Run 数量查询失败" >&2; return 1; }
  case "$result" in
    ''|*[!0-9]*) echo "全部 V2 Run 数量无效" >&2; return 1 ;;
  esac
  printf '%s\n' "$result"
}

initialize_joint_drain_indexes() {
  require_joint_drain_assets
  command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; return 1; }
  docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; return 1; }
  v1_marker="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T redis redis-cli --raw GET inkforge:runs:drain:index-version | tr -d '\r')" || return 1
  v2_marker="$(timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T execution-redis redis-cli --raw GET inkforge:executions:drain:index-version | tr -d '\r')" || return 1
  case "$v1_marker:$v2_marker" in
    1:1) printf '%s\n' 'drain-indexes-ready:v1=existing:v2=existing'; return 0 ;;
    :) ;;
    1:|:1) echo "V1/V2 drain 索引 marker 只存在一侧，禁止猜测补齐" >&2; return 1 ;;
    *) echo "drain 索引 marker 版本损坏，禁止初始化" >&2; return 1 ;;
  esac
  current_state="$(query_schema_state)"
  [ "$current_state" = "migrated-empty-v2" ] || {
    if [ "$current_state" = "migrated-with-v2" ]; then
      timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
        exec -T execution-redis redis-cli --raw SET \
          inkforge:executions:restore:quarantine \
          drain-index-missing-with-v2-database NX >/dev/null || true
      echo "已有 V2 数据时禁止初始化空 execution drain 索引，已要求具名 quarantine 审计" >&2
    else
      echo "drain 索引初始化要求完整迁移后且全部 V2 Run 为零" >&2
    fi
    return 1
  }
  core_config="$(read_running_core_drain_config)" || return 1
  [ "$(printf '%s\n' "$core_config" | sed -n '1p')" = "true" ] \
    && [ "$(printf '%s\n' "$core_config" | sed -n '2p')" = "off" ] \
    && [ "$(printf '%s\n' "$core_config" | sed -n '3p')" = "false" ] || {
      echo "初始化 drain 索引前运行 Core 必须 schemaReady=true、V2 route=off、V1 fresh=false" >&2
      return 1
    }
  timeout 10 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T agent-service python -c \
      'from inkforge_agents.queue.repository import QUEUE_DRAIN_INDEX_VERSION; from inkforge_agents.execution.journal import EXECUTION_DRAIN_INDEX_VERSION; assert QUEUE_DRAIN_INDEX_VERSION == EXECUTION_DRAIN_INDEX_VERSION == "1"' \
      >/dev/null || {
        echo "运行 Agent 镜像未证明支持 drain 索引生产者" >&2
        return 1
      }
  before_count="$(query_all_v2_run_count)" || return 1
  [ "$before_count" = "0" ] || {
    echo "初始化前 PostgreSQL 已存在 V2 Run" >&2
    return 1
  }
  v1_initialize_source="$(cat "$v1_drain_index_initialize_lua")" || return 1
  v1_result="$(timeout 20 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T redis redis-cli --raw EVAL "$v1_initialize_source" 0 | tr -d '\r')" || {
      echo "V1 drain 索引初始化失败" >&2
      return 1
    }
  case "$v1_result" in initialized|existing) ;; *) echo "V1 drain 索引不能安全初始化：$v1_result" >&2; return 1 ;; esac
  v2_initialize_source="$(cat "$v2_drain_index_initialize_lua")" || return 1
  v2_result="$(timeout 20 docker compose --env-file "$env_file" -f "$compose_file" \
    exec -T execution-redis redis-cli --raw EVAL "$v2_initialize_source" 0 | tr -d '\r')" || {
      echo "V2 drain 索引初始化失败" >&2
      return 1
    }
  case "$v2_result" in initialized|existing) ;; *) echo "V2 drain 索引不能安全初始化：$v2_result" >&2; return 1 ;; esac
  after_count="$(query_all_v2_run_count)" || return 1
  [ "$after_count" = "0" ] || {
    echo "drain 索引初始化期间出现 V2 Run，证据无效" >&2
    return 1
  }
  printf 'drain-indexes-ready:v1=%s:v2=%s\n' "$v1_result" "$v2_result"
}

joint_drain_report() {
  current_state="$(query_schema_state)"
  case "$current_state" in
    migrated-empty-v2|migrated-with-v2) ;;
    unmigrated) echo "联合 drain 状态要求完整 V2 迁移结构" >&2; return 1 ;;
    partial) echo "schema-state:partial" >&2; return 1 ;;
    *) echo "schema-state:invalid-result" >&2; return 1 ;;
  esac
  command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; return 1; }
  docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; return 1; }
  [ -r "$compose_file" ] || { echo "生产 Compose 文件不可读" >&2; return 1; }
  require_joint_drain_assets
  write_runtime_topology "$temp_dir/drain-runtime-before.json" || return 1
  query_joint_drain_postgres > "$temp_dir/drain-postgres-before.json" || {
    echo "联合 drain PostgreSQL PG1 快照失败" >&2
    return 1
  }
  [ -s "$temp_dir/drain-postgres-before.json" ] || {
    echo "联合 drain PostgreSQL PG1 快照为空" >&2
    return 1
  }
  require_joint_drain_redis_health
  read_joint_drain_redis redis "$v1_queue_snapshot_lua" \
    "$temp_dir/drain-v1-redis.json" || return 1
  read_joint_drain_redis execution-redis "$v2_execution_snapshot_lua" \
    "$temp_dir/drain-v2-redis.json" || return 1
  query_joint_drain_postgres > "$temp_dir/drain-postgres-after.json" || {
    echo "联合 drain PostgreSQL PG2 快照失败" >&2
    return 1
  }
  [ -s "$temp_dir/drain-postgres-after.json" ] || {
    echo "联合 drain PostgreSQL PG2 快照为空" >&2
    return 1
  }
  write_runtime_topology "$temp_dir/drain-runtime-after.json" || return 1
  python3 "$joint_drain_builder" build \
    --database "$target_database" \
    --runtime-before "$temp_dir/drain-runtime-before.json" \
    --postgres-before "$temp_dir/drain-postgres-before.json" \
    --ordinary-redis "$temp_dir/drain-v1-redis.json" \
    --execution-redis "$temp_dir/drain-v2-redis.json" \
    --postgres-after "$temp_dir/drain-postgres-after.json" \
    --runtime-after "$temp_dir/drain-runtime-after.json"
}

boundary_drain_report() {
  require_boundary_drain_assets
  command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; return 1; }
  docker compose version >/dev/null 2>&1 || { echo "缺少 docker compose" >&2; return 1; }
  current_state="$(query_schema_state)" || return 1
  core_config="$(read_running_core_drain_config)" || return 1
  schema_ready="$(printf '%s\n' "$core_config" | sed -n '1p')"
  route_mode="$(printf '%s\n' "$core_config" | sed -n '2p')"
  v1_fresh="$(printf '%s\n' "$core_config" | sed -n '3p')"
  [ "$route_mode" = off ] && [ "$v1_fresh" = false ] || {
    echo "boundary drain 要求 route-off 与 V1 fresh=false" >&2
    return 1
  }
  write_runtime_topology "$temp_dir/boundary-runtime-before.json" || return 1
  case "$current_state:$schema_ready" in
    unmigrated:false)
      query_before=query_pre_contract_drain_postgres
      build_state=unmigrated
      ;;
    migrated-empty-v2:false)
      query_before=query_joint_drain_postgres
      build_state=migrated-empty-v2-closed
      ;;
    migrated-empty-v2:true|migrated-with-v2:true)
      joint_drain_report > "$temp_dir/boundary-joint-report.json" || return 1
      write_runtime_topology "$temp_dir/boundary-runtime-after.json" || return 1
      python3 "$boundary_builder" build-live \
        --database "$target_database" --schema-state "$current_state" \
        --topology-before "$temp_dir/boundary-runtime-before.json" \
        --topology-after "$temp_dir/boundary-runtime-after.json" \
        --joint-report "$temp_dir/boundary-joint-report.json"
      return
      ;;
    partial:*) echo "schema-state:partial" >&2; return 1 ;;
    *) echo "boundary drain schema/config 不兼容" >&2; return 1 ;;
  esac
  "$query_before" > "$temp_dir/boundary-postgres-before.json" || return 1
  require_joint_drain_redis_health
  read_joint_drain_redis redis "$v1_pre_activation_snapshot_lua" \
    "$temp_dir/boundary-v1-redis.json" || return 1
  read_joint_drain_redis execution-redis "$v2_pre_activation_snapshot_lua" \
    "$temp_dir/boundary-v2-redis.json" || return 1
  "$query_before" > "$temp_dir/boundary-postgres-after.json" || return 1
  write_runtime_topology "$temp_dir/boundary-runtime-after.json" || return 1
  python3 "$boundary_builder" build-live \
    --database "$target_database" --schema-state "$build_state" \
    --topology-before "$temp_dir/boundary-runtime-before.json" \
    --topology-after "$temp_dir/boundary-runtime-after.json" \
    --postgres-before "$temp_dir/boundary-postgres-before.json" \
    --postgres-after "$temp_dir/boundary-postgres-after.json" \
    --ordinary-redis "$temp_dir/boundary-v1-redis.json" \
    --execution-redis "$temp_dir/boundary-v2-redis.json"
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

read_core_schema_profile() {
  # Core 自己的 capability 投影决定实时 guard 比较哪一份精确结构；这里只读取三个非敏感布尔开关和数据库名。
  compose exec -T \
    -e INKFORGE_EXPECTED_DATABASE="$target_database" \
    core-api /bin/sh -ec '
      database_without_query=${DATABASE_URL%%\?*}
      case "$database_without_query" in
        */"$INKFORGE_EXPECTED_DATABASE") ;;
        *) exit 31 ;;
      esac
      normalize_bool() {
        value=$(printf "%s" "$1" | tr "[:upper:]" "[:lower:]")
        case "$value" in
          true|1) printf "true\n" ;;
          ""|false|0) printf "false\n" ;;
          *) exit 32 ;;
        esac
      }
      video=$(normalize_bool "${VIDEO_PREVIEW_ENABLED:-false}")
      phone_enabled=$(normalize_bool "${PHONE_AUTH_ENABLED:-false}")
      phone_send=$(normalize_bool "${PHONE_AUTH_SEND_ENABLED:-false}")
      phone=false
      [ "$phone_enabled" != true ] || [ "$phone_send" != true ] || phone=true
      case "$video:$phone" in
        true:true) printf "full\n" ;;
        false:true) printf "without-video-preview\n" ;;
        true:false) printf "without-phone-auth\n" ;;
        false:false) printf "without-video-preview-and-phone-auth\n" ;;
        *) exit 33 ;;
      esac
    '
}

read_live_guard_fingerprint() {
  fingerprint="$(compose exec -T core-api /usr/local/bin/inkforge-schema-guard | tr -d '\r')" || {
    echo "实时 Java schema guard 无法生成 fingerprint" >&2
    exit 1
  }
  case "$fingerprint" in
    ""|*[!0-9a-f]*|*'\n'*)
      echo "实时 Java schema guard fingerprint 格式无效" >&2
      exit 1
      ;;
  esac
  [ "${#fingerprint}" -eq 64 ] || {
    echo "实时 Java schema guard fingerprint 格式无效" >&2
    exit 1
  }
  printf '%s\n' "$fingerprint"
}

read_live_source_json() {
  PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000' \
    timeout 45 psql -X -v ON_ERROR_STOP=1 \
      -v expected_database="$target_database" -Atq "$database_url" <<'SQL'
SELECT pg_catalog.json_build_object(
  'databaseName', pg_catalog.current_database(),
  'serverAddress', pg_catalog.inet_server_addr()::text,
  'serverPort', pg_catalog.inet_server_port(),
  'serverVersion', pg_catalog.current_setting('server_version'),
  'serverVersionNum', pg_catalog.current_setting('server_version_num')::integer
)::text
WHERE pg_catalog.current_database() = :'expected_database';
SQL
}

dump_schema_only() {
  output_path=$1
  PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=120000 -c lock_timeout=5000' \
    timeout 180 pg_dump --schema-only --no-owner --no-acl --format=plain \
      --file "$output_path" "$database_url"
  [ -s "$output_path" ] || {
    echo "PostgreSQL schema-only 导出为空" >&2
    exit 1
  }
  # PostgreSQL 安全更新会为每次 pg_dump 生成随机 \restrict/\unrestrict key；证据不用于恢复，
  # 删除这两个非结构控制行后再取 SHA，避免同一只读结构在立即复验时产生伪漂移。
  python3 - "$output_path" <<'PY'
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
normalized = "".join(
    line
    for line in lines
    if re.fullmatch(r"\\(?:un)?restrict [^\r\n]+\r?\n?", line) is None
)
with path.open("w", encoding="utf-8", newline="\n") as output:
    output.write(normalized)
    output.flush()
    os.fsync(output.fileno())
PY
  chmod 600 "$output_path"
}

resolve_contract_evidence_dir() {
  mode=$1
  requested="${DURABLE_AGENT_CONTRACT_EVIDENCE_DIR:-}"
  [ -n "$requested" ] || { echo "结构证据动作必须显式指定证据目录" >&2; exit 1; }
  python3 - "$requested" "$app_dir" "$mode" <<'PY'
import re
import sys
from pathlib import Path

requested = Path(sys.argv[1])
app_dir = Path(sys.argv[2]).resolve(strict=True)
mode = sys.argv[3]
if not requested.is_absolute() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", requested.name):
    print("contract-evidence-path:invalid", file=sys.stderr)
    raise SystemExit(1)
try:
    parent = requested.parent.resolve(strict=True)
except OSError:
    print("contract-evidence-parent:invalid", file=sys.stderr)
    raise SystemExit(1) from None
if any(candidate.is_symlink() for candidate in (requested.parent, *requested.parent.parents)):
    print("contract-evidence-path:symlink-ancestor", file=sys.stderr)
    raise SystemExit(1)
if parent == app_dir or app_dir in parent.parents:
    print("contract-evidence-path:repository-or-symlink", file=sys.stderr)
    raise SystemExit(1)
target = parent / requested.name
if mode == "export":
    if target.exists() or target.is_symlink():
        print("contract-evidence-path:already-exists", file=sys.stderr)
        raise SystemExit(1)
elif mode == "verify":
    if not target.is_dir() or target.is_symlink():
        print("contract-evidence-path:not-directory", file=sys.stderr)
        raise SystemExit(1)
else:
    raise SystemExit(2)
print(target)
PY
}

publish_contract_evidence_dir() {
  source_dir=$1
  target_dir=$2
  python3 - "$source_dir" "$target_dir" <<'PY'
import ctypes
import errno
import os
import sys
from pathlib import Path

source = os.fsencode(Path(sys.argv[1]))
target = os.fsencode(Path(sys.argv[2]))
library = ctypes.CDLL(None, use_errno=True)
if sys.platform.startswith("linux"):
    rename = library.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    status = rename(-100, source, -100, target, 1)  # AT_FDCWD + RENAME_NOREPLACE
elif sys.platform == "darwin":
    rename = library.renamex_np
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    status = rename(source, target, 4)  # RENAME_EXCL
else:
    print("contract-evidence-publish:unsupported-platform", file=sys.stderr)
    raise SystemExit(1)
if status != 0:
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        print("contract-evidence-publish:target-exists", file=sys.stderr)
    else:
        print(f"contract-evidence-publish:rename-failed:{error}", file=sys.stderr)
    raise SystemExit(1)
parent_descriptor = os.open(Path(sys.argv[2]).parent, os.O_RDONLY)
try:
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
PY
}

require_migrated_contract_state() {
  contract_state="$(query_schema_state)"
  case "$contract_state" in
    migrated-empty-v2|migrated-with-v2) printf '%s\n' "$contract_state" ;;
    unmigrated) echo "结构证据只允许从完整迁移后结构创建或复验" >&2; exit 1 ;;
    partial) echo "schema-state:partial" >&2; exit 1 ;;
    *) echo "schema-state:invalid-result" >&2; exit 1 ;;
  esac
}

verify_contract_evidence_checksums() {
  checksum_evidence_dir=$1
  python3 - "$checksum_evidence_dir" <<'PY'
import os
import re
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
allowed = {
    "schema-contract.json",
    "schema-only.sql",
    "contract-verification.meta",
    "SHA256SUMS",
}
items = list(root.iterdir())
root_metadata = root.stat()
if stat.S_IMODE(root_metadata.st_mode) != 0o700 or (
    hasattr(os, "getuid") and root_metadata.st_uid != os.getuid()
):
    print("contract-evidence-directory:owner-or-mode", file=sys.stderr)
    raise SystemExit(1)
if {item.name for item in items} != allowed or any(
    item.is_symlink()
    or not item.is_file()
    or stat.S_IMODE(item.stat().st_mode) != 0o600
    or (hasattr(os, "getuid") and item.stat().st_uid != os.getuid())
    for item in items
):
    print("contract-evidence-files:invalid", file=sys.stderr)
    raise SystemExit(1)
lines = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
expected_names = allowed - {"SHA256SUMS"}
names = []
for line in lines:
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
    if match is None:
        print("contract-evidence-checksums:invalid", file=sys.stderr)
        raise SystemExit(1)
    names.append(match.group(2))
if len(names) != len(set(names)) or set(names) != expected_names:
    print("contract-evidence-checksums:unexpected-files", file=sys.stderr)
    raise SystemExit(1)
PY
  (
    cd -- "$checksum_evidence_dir"
    sha256sum --check SHA256SUMS >/dev/null
  ) || { echo "结构证据 SHA256SUMS 校验失败" >&2; exit 1; }
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
    boundary_driver="${DURABLE_AGENT_BOUNDARY_DRIVER:-}"
    ddl_boundary="${DURABLE_AGENT_DDL_BOUNDARY:-}"
    [ -n "$boundary_driver" ] || {
      echo "生产 DDL 必须设置 boundary driver" >&2
      exit 1
    }
    [ -n "$ddl_boundary" ] || {
      echo "生产 DDL 必须设置唯一 boundary" >&2
      exit 1
    }
    [ "$boundary_driver" = "$app_dir/scripts/durable-agent-v2-release.sh" ] \
      && [ -f "$boundary_driver" ] && [ ! -L "$boundary_driver" ] \
      && [ -r "$boundary_driver" ] || {
      echo "生产 DDL boundary driver 不是当前 trusted control driver" >&2
      exit 1
    }
    sh "$boundary_driver" consume-live-boundary "$ddl_boundary" >/dev/null
  fi
  PGOPTIONS="$pg_options" timeout 240 psql -X -v ON_ERROR_STOP=1 \
    "$database_url" -f "$execution_sql" >/dev/null
  if [ "$target_database" = "novelwriter" ]; then
    sh "$boundary_driver" mark-live-boundary-applied "$ddl_boundary" >/dev/null
  fi
}

case "$action" in
  status)
    query_schema_state
    ;;
  active-v2-count)
    query_active_v2_run_count
    ;;
  initialize-drain-indexes)
    initialize_joint_drain_indexes
    ;;
  drain-status)
    joint_drain_report
    ;;
  verify-drain)
    joint_drain_report > "$temp_dir/drain-report.json" || {
      echo "联合 drain 状态读取失败" >&2
      exit 1
    }
    python3 "$joint_drain_builder" verify --report "$temp_dir/drain-report.json"
    ;;
  boundary-drain)
    boundary_drain_report
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
  export-contract)
    command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
    command -v pg_dump >/dev/null 2>&1 || { echo "缺少 pg_dump" >&2; exit 1; }
    contract_state="$(require_migrated_contract_state)"
    require_compatible_core_and_exact_contract
    contract_profile="$(read_core_schema_profile)" || {
      echo "无法读取当前 Core 的数据库身份与 schema profile" >&2
      exit 1
    }
    live_guard_fingerprint="$(read_live_guard_fingerprint)"
    evidence_dir="$(resolve_contract_evidence_dir export)" || {
      echo "结构证据目录无法安全解析" >&2
      exit 1
    }
    evidence_parent="$(dirname -- "$evidence_dir")"
    evidence_name="$(basename -- "$evidence_dir")"
    contract_evidence_temp_dir="$(
      mktemp -d "$evidence_parent/.${evidence_name}.partial.XXXXXX"
    )"
    chmod 700 "$contract_evidence_temp_dir"
    read_live_source_json > "$contract_evidence_temp_dir/source.json" || {
      echo "无法读取实时 PostgreSQL 来源元数据" >&2
      exit 1
    }
    chmod 600 "$contract_evidence_temp_dir/source.json"
    dump_schema_only "$contract_evidence_temp_dir/schema-only.sql"
    schema_only_sha="$(
      sha256sum "$contract_evidence_temp_dir/schema-only.sql" | cut -d ' ' -f 1
    )"
    contract_fingerprint="$(python3 "$contract_evidence_builder" build \
      --post-contract "$post_contract" \
      --evidence-dir "$contract_evidence_temp_dir" \
      --database "$target_database" \
      --schema-state "$contract_state" \
      --profile "$contract_profile" \
      --guard-fingerprint "$live_guard_fingerprint" \
      --post-contract-sha256 "$post_contract_sha" \
      --schema-only-sha256 "$schema_only_sha" \
      --source-json "$contract_evidence_temp_dir/source.json"
    )" || {
      echo "迁移后结构证据构建失败" >&2
      exit 1
    }
    rm -f -- "$contract_evidence_temp_dir/source.json"
    (
      cd -- "$contract_evidence_temp_dir"
      sha256sum schema-contract.json schema-only.sql contract-verification.meta \
        > SHA256SUMS
      chmod 600 SHA256SUMS
    )
    verify_contract_evidence_checksums "$contract_evidence_temp_dir"
    python3 - "$contract_evidence_temp_dir" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
for path in root.iterdir():
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
descriptor = os.open(root, os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
    publish_contract_evidence_dir "$contract_evidence_temp_dir" "$evidence_dir"
    contract_evidence_temp_dir=""
    printf 'contract-export-ok:%s:%s\n' "$evidence_dir" "$contract_fingerprint"
    ;;
  verify-contract)
    command -v docker >/dev/null 2>&1 || { echo "缺少 docker" >&2; exit 1; }
    command -v pg_dump >/dev/null 2>&1 || { echo "缺少 pg_dump" >&2; exit 1; }
    contract_state="$(require_migrated_contract_state)"
    require_compatible_core_and_exact_contract
    contract_profile="$(read_core_schema_profile)" || {
      echo "无法读取当前 Core 的数据库身份与 schema profile" >&2
      exit 1
    }
    live_guard_fingerprint="$(read_live_guard_fingerprint)"
    evidence_dir="$(resolve_contract_evidence_dir verify)" || {
      echo "结构证据目录无法安全解析" >&2
      exit 1
    }
    verify_contract_evidence_checksums "$evidence_dir"
    read_live_source_json > "$temp_dir/source.json" || {
      echo "无法读取实时 PostgreSQL 来源元数据" >&2
      exit 1
    }
    chmod 600 "$temp_dir/source.json"
    dump_schema_only "$temp_dir/schema-only.current.sql"
    schema_only_sha="$(sha256sum "$temp_dir/schema-only.current.sql" | cut -d ' ' -f 1)"
    contract_fingerprint="$(python3 "$contract_evidence_builder" verify \
      --post-contract "$post_contract" \
      --evidence-dir "$evidence_dir" \
      --database "$target_database" \
      --schema-state "$contract_state" \
      --profile "$contract_profile" \
      --guard-fingerprint "$live_guard_fingerprint" \
      --post-contract-sha256 "$post_contract_sha" \
      --schema-only-sha256 "$schema_only_sha" \
      --source-json "$temp_dir/source.json"
    )" || {
      echo "迁移后结构证据复验失败" >&2
      exit 1
    }
    printf 'contract-verify-ok:%s:%s\n' "$evidence_dir" "$contract_fingerprint"
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
