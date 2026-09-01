from __future__ import annotations

from pathlib import Path

from tests.architecture.durable_agent_execution_fixtures import (
    BASE_SCHEMA,
    _psql,
    _scalar,
)

ROOT = Path(__file__).parents[2]
FORWARD = ROOT / "scripts" / "migrations" / "20260831_durable_agent_execution.sql"
ROLLBACK = (
    ROOT
    / "scripts"
    / "migrations"
    / "20260831_durable_agent_execution.rollback.sql"
)
RUN_COLUMNS = {
    "engineVersion",
    "workflow",
    "operation",
    "operationCatalogVersion",
    "writingSessionId",
    "parentRunId",
    "idempotencyKey",
    "requestHash",
    "targetType",
    "targetId",
    "budgetJson",
    "modelPolicyJson",
    "currentEvidenceBundleId",
    "lastEventSequence",
    "revision",
    "cancelRequestId",
    "cancelRequestedAt",
    "completedAt",
    "errorCode",
}

STEP_COLUMNS = {
    "ordinal",
    "purpose",
    "lane",
    "attemptCount",
    "nextAttemptAt",
    "fencingToken",
    "leaseExpiresAt",
    "heartbeatAt",
    "activeJobId",
    "idempotencyKey",
    "requestHash",
    "inputHash",
    "resultHash",
    "evidenceBundleId",
    "artifactId",
    "artifactRevision",
    "modelProfile",
    "modelProfileVersion",
    "outputSchema",
    "outputSchemaVersion",
    "budgetJson",
    "resolvedModelJson",
    "usageJson",
    "lastProgressSequence",
    "cancelRequestId",
    "submittedAt",
    "updatedAt",
    "completedAt",
    "errorCode",
}

NEW_TABLES = {
    "WorkflowEvidenceBundle",
    "WorkflowEvidenceItem",
    "WorkflowEvent",
    "WorkflowEvaluation",
    "WorkflowBillingReservation",
}


def test_named_scripts_keep_the_approved_scope_and_database_guards() -> None:
    forward = FORWARD.read_text(encoding="utf-8")
    rollback = ROLLBACK.read_text(encoding="utf-8")

    assert "SET LOCAL search_path = pg_catalog, public" in forward
    assert "SET LOCAL search_path = pg_catalog, public" in rollback
    assert "SET LOCAL lock_timeout = '5s'" in forward
    assert "SET LOCAL statement_timeout = '120s'" in forward
    assert "pg_catalog.current_database() = 'novelwriterdev'" in forward
    assert "novelwriter:20260831:apply" in forward
    assert "novelwriter:20260831:rollback-empty-v2" in rollback
    assert 'WHERE "engineVersion" = 2' in rollback
    assert "拒绝耐久 Agent 执行 DDL 回滚" in rollback

    for table in NEW_TABLES:
        assert f'CREATE TABLE IF NOT EXISTS public."{table}"' in forward
    assert 'CREATE TABLE IF NOT EXISTS "WorkflowRun"' not in forward
    assert 'CREATE TABLE IF NOT EXISTS "WorkflowStep"' not in forward
    assert "WritingTask" not in forward
    assert "WritingRunCommand" not in forward
    assert "WritingEventOutbox" not in forward

    for column in RUN_COLUMNS | STEP_COLUMNS:
        assert f'"{column}"' in forward or f" {column} " in forward
    assert 'ALTER COLUMN "novelId" DROP NOT NULL' in forward
    assert 'ALTER COLUMN "chapterId" DROP NOT NULL' in forward
    assert 'ALTER COLUMN "novelId" SET NOT NULL' in rollback
    assert 'ALTER COLUMN "chapterId" SET NOT NULL' in rollback
    assert 'CREATE OR REPLACE FUNCTION public."rejectWorkflowAuditMutation"()' in forward
    assert (
        'CREATE OR REPLACE FUNCTION public."rejectWorkflowRunV2IdentityMutation"()'
        in forward
    )
    assert (
        'CREATE OR REPLACE FUNCTION public."rejectWorkflowStepV2IdentityMutation"()'
        in forward
    )
    assert forward.count("BEFORE UPDATE OR DELETE ON public.\"WorkflowRun\"") == 1
    assert forward.count("BEFORE UPDATE OR DELETE ON public.\"WorkflowStep\"") == 1
    assert 'DROP FUNCTION IF EXISTS public."rejectWorkflowAuditMutation"()' in rollback
    assert (
        'DROP FUNCTION IF EXISTS public."rejectWorkflowRunV2IdentityMutation"()'
        in rollback
    )
    assert (
        'DROP FUNCTION IF EXISTS public."rejectWorkflowStepV2IdentityMutation"()'
        in rollback
    )
    assert "DROP TABLE IF EXISTS public.\"WorkflowEvaluation\" CASCADE" not in rollback


def test_postgres14_forward_constraints_rollback_and_reforward(
    isolated_postgres: tuple[str, str],
) -> None:
    docker, container = isolated_postgres

    # PostgreSQL 14 的 public schema 默认可创建对象；恶意同名函数不能遮蔽迁移门禁。
    _psql(docker, container, 'CREATE DATABASE "migration-shadow";')
    _psql(
        docker,
        container,
        """
        CREATE ROLE migration_attacker;
        SET ROLE migration_attacker;
        CREATE FUNCTION public.current_database()
        RETURNS name
        LANGUAGE SQL
        IMMUTABLE
        AS 'SELECT ''novelwriterdev''::name';
        RESET ROLE;
        """,
        database="migration-shadow",
    )
    shadowed_forward = _psql(
        docker,
        container,
        FORWARD.read_text(encoding="utf-8"),
        database="migration-shadow",
        check=False,
    )
    assert shadowed_forward.returncode != 0
    assert "当前数据库为 migration-shadow" in shadowed_forward.stderr
    shadowed_rollback = _psql(
        docker,
        container,
        ROLLBACK.read_text(encoding="utf-8"),
        database="migration-shadow",
        check=False,
    )
    assert shadowed_rollback.returncode != 0
    assert "当前数据库为 migration-shadow" in shadowed_rollback.stderr

    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))

    # 先写一组当前契约的 V1 数据，证明迁移不回填也不破坏旧行。
    _psql(
        docker,
        container,
        """
        INSERT INTO "User" (id, username, "passwordHash", "updatedAt")
        VALUES
          ('migration-user', 'migration-user', 'hash', CURRENT_TIMESTAMP),
          ('other-user', 'other-user', 'hash', CURRENT_TIMESTAMP);
        INSERT INTO "Novel" (id, name, "userId", "updatedAt")
        VALUES
          ('migration-novel', 'migration-novel', 'migration-user', CURRENT_TIMESTAMP),
          ('other-novel', 'other-novel', 'other-user', CURRENT_TIMESTAMP);
        INSERT INTO "Chapter" (
          id, "novelId", title, content, "order", "updatedAt"
        ) VALUES
          ('migration-chapter', 'migration-novel', 'chapter', '', 1, CURRENT_TIMESTAMP),
          ('other-chapter', 'other-novel', 'chapter', '', 1, CURRENT_TIMESTAMP);
        INSERT INTO "WritingSession" (
          id, "novelId", "chapterId", "updatedAt"
        ) VALUES
          ('migration-session', 'migration-novel', 'migration-chapter', CURRENT_TIMESTAMP),
          ('other-session', 'other-novel', 'other-chapter', CURRENT_TIMESTAMP);
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt"
        ) VALUES (
          'legacy-run', 'migration-novel', 'migration-chapter', 'migration-user',
          'chat', 'completed', CURRENT_TIMESTAMP
        );
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status
        ) VALUES ('legacy-step', 'legacy-run', 'tool', 'completed');
        """,
    )

    forward = FORWARD.read_text(encoding="utf-8")
    rollback = ROLLBACK.read_text(encoding="utf-8")
    _psql(docker, container, forward)
    _psql(docker, container, forward)

    run_columns = _scalar(
        docker,
        container,
        """
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'WorkflowRun'
          AND column_name = ANY (ARRAY[
            'engineVersion', 'workflow', 'operation', 'operationCatalogVersion',
            'writingSessionId', 'parentRunId', 'idempotencyKey', 'requestHash',
            'targetType', 'targetId', 'budgetJson', 'modelPolicyJson',
            'currentEvidenceBundleId', 'lastEventSequence', 'revision',
            'cancelRequestId', 'cancelRequestedAt', 'completedAt', 'errorCode'
          ]);
        """,
    )
    step_columns = _scalar(
        docker,
        container,
        """
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'WorkflowStep'
          AND column_name = ANY (ARRAY[
            'ordinal', 'purpose', 'lane', 'attemptCount', 'nextAttemptAt',
            'fencingToken', 'leaseExpiresAt', 'heartbeatAt', 'activeJobId',
            'idempotencyKey', 'requestHash', 'inputHash', 'resultHash',
            'evidenceBundleId', 'artifactId', 'artifactRevision', 'modelProfile',
            'modelProfileVersion', 'outputSchema', 'outputSchemaVersion', 'budgetJson',
            'resolvedModelJson', 'usageJson', 'lastProgressSequence', 'cancelRequestId',
            'submittedAt', 'updatedAt', 'completedAt', 'errorCode'
          ]);
        """,
    )
    assert run_columns == str(len(RUN_COLUMNS))
    assert step_columns == str(len(STEP_COLUMNS))
    assert _scalar(
        docker,
        container,
        """
        SELECT count(*)
        FROM pg_class
        WHERE oid = ANY (ARRAY[
          to_regclass('public."WorkflowEvidenceBundle"'),
          to_regclass('public."WorkflowEvidenceItem"'),
          to_regclass('public."WorkflowEvent"'),
          to_regclass('public."WorkflowEvaluation"'),
          to_regclass('public."WorkflowBillingReservation"')
        ]);
        """,
    ) == str(len(NEW_TABLES))
    assert _scalar(
        docker,
        container,
        """
        SELECT (
          run."engineVersion" IS NULL
          AND run.workflow IS NULL
          AND run.revision IS NULL
          AND step.ordinal IS NULL
          AND step."attemptCount" IS NULL
        )::text
        FROM "WorkflowRun" AS run
        JOIN "WorkflowStep" AS step ON step."runId" = run.id
        WHERE run.id = 'legacy-run';
        """,
    ) == "true"

    invalid_v1_scope = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt"
        ) VALUES (
          'invalid-v1-scope', NULL, NULL, 'migration-user', 'chat', 'pending',
          CURRENT_TIMESTAMP
        );
        """,
        check=False,
    )
    assert invalid_v1_scope.returncode != 0
    assert "WorkflowRun_v1_scope_check" in invalid_v1_scope.stderr

    # user scope 的 V2 运行不需要伪造小说或章节。
    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "idempotencyKey", "requestHash", "targetType", "targetId",
          "budgetJson", "modelPolicyJson", "lastEventSequence", revision
        ) VALUES (
          'style-run', NULL, NULL, 'migration-user', 'chat', 'running',
          CURRENT_TIMESTAMP, 2, 'style', 'portrait', 'catalog-v1',
          'style-request', repeat('1', 64), 'style_profile', 'style-1',
          '{}', '{}', 0, 1
        );
        """,
    )

    cross_tenant_run = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "idempotencyKey", "requestHash", "budgetJson", "modelPolicyJson",
          "lastEventSequence", revision
        ) VALUES (
          'cross-tenant-run', 'other-novel', 'other-chapter', 'migration-user',
          'chat', 'running', CURRENT_TIMESTAMP, 2, 'long_serial', 'answer_question',
          'catalog-v1', 'cross-tenant-request', repeat('2', 64), '{}', '{}', 0, 1
        );
        """,
        check=False,
    )
    assert cross_tenant_run.returncode != 0
    assert "WorkflowRun_novel_user_fkey" in cross_tenant_run.stderr

    cross_session_run = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "writingSessionId", "idempotencyKey", "requestHash", "budgetJson",
          "modelPolicyJson", "lastEventSequence", revision
        ) VALUES (
          'cross-session-run', 'migration-novel', 'migration-chapter', 'migration-user',
          'chat', 'running', CURRENT_TIMESTAMP, 2, 'long_serial', 'answer_question',
          'catalog-v1', 'other-session', 'cross-session-request', repeat('3', 64),
          '{}', '{}', 0, 1
        );
        """,
        check=False,
    )
    assert cross_session_run.returncode != 0
    assert "WorkflowRun_writingSession_scope_fkey" in cross_session_run.stderr

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "idempotencyKey", "requestHash", "budgetJson", "modelPolicyJson",
          "lastEventSequence", revision
        ) VALUES (
          'other-parent', 'other-novel', 'other-chapter', 'other-user', 'chat',
          'running', CURRENT_TIMESTAMP, 2, 'long_serial', 'answer_question',
          'catalog-v1', 'other-parent-request', repeat('4', 64), '{}', '{}', 0, 1
        );
        """,
    )
    cross_parent_run = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "parentRunId", "idempotencyKey", "requestHash", "budgetJson",
          "modelPolicyJson", "lastEventSequence", revision
        ) VALUES (
          'cross-parent-run', 'migration-novel', 'migration-chapter', 'migration-user',
          'chat', 'running', CURRENT_TIMESTAMP, 2, 'long_serial', 'answer_question',
          'catalog-v1', 'other-parent', 'cross-parent-request', repeat('5', 64),
          '{}', '{}', 0, 1
        );
        """,
        check=False,
    )
    assert cross_parent_run.returncode != 0
    assert "WorkflowRun_parent_user_fkey" in cross_parent_run.stderr

    # 写入一条完整的 V2 纵切骨架，覆盖 Evidence、Event、Step、Artifact revision 和 Evaluation。
    _psql(
        docker,
        container,
        """
        BEGIN;
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "writingSessionId", "idempotencyKey", "requestHash", "targetType", "targetId",
          "budgetJson", "modelPolicyJson", "lastEventSequence", revision
        ) VALUES (
          'v2-run', 'migration-novel', 'migration-chapter', 'migration-user', 'chat', 'running',
          CURRENT_TIMESTAMP, 2, 'long_serial', 'rewrite_chapter_selection', 'catalog-v1',
          'migration-session', 'request-1', repeat('a', 64), 'chapter_selection', 'selection-1',
          '{}', '{}', 1, 1
        );
        INSERT INTO "WorkflowEvidenceBundle" (
          id, "runId", version, "policyVersion", "manifestJson",
          "manifestSha256", "totalBytes"
        ) VALUES (
          'bundle-1', 'v2-run', 1, 'policy-v1', '{}', repeat('b', 64), 3
        );
        UPDATE "WorkflowRun"
        SET "currentEvidenceBundleId" = 'bundle-1'
        WHERE id = 'v2-run';
        INSERT INTO "WorkflowEvidenceItem" (
          id, "bundleId", ordinal, "resourceType", "resourceId", exists, "contentType",
          "contentText", "contentSha256", "byteCount"
        ) VALUES (
          'item-1', 'bundle-1', 1, 'chapter_selection', 'selection-1',
          TRUE, 'text', 'abc', repeat('c', 64), 3
        );
        INSERT INTO "WorkflowEvidenceItem" (
          id, "bundleId", ordinal, "resourceType", "resourceId", exists,
          "byteCount", "metadataJson"
        ) VALUES (
          'item-absence', 'bundle-1', 2, 'beat_plan', 'missing-plan', FALSE,
          0, '{"absenceSentinel":"not_found"}'
        );
        INSERT INTO "WorkflowEvent" (
          id, "runId", sequence, "eventType", "payloadJson", "dedupeKey"
        ) VALUES ('event-1', 'v2-run', 1, 'run_accepted', '{}', 'accepted');
        INSERT INTO "ReviewArtifact" (
          id, "novelId", "workflowRunId", kind, status, "payloadJson", "updatedAt"
        ) VALUES (
          'artifact-1', 'migration-novel', 'v2-run', 'chapter_content',
          'under_review', '{}', CURRENT_TIMESTAMP
        );
        INSERT INTO "ReviewArtifactRevision" (
          id, "artifactId", revision, "payloadJson"
        ) VALUES ('artifact-revision-1', 'artifact-1', 1, '{}');
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status, ordinal, purpose, lane,
          "attemptCount", "fencingToken", "idempotencyKey", "requestHash",
          "inputHash", "resultHash", "evidenceBundleId", "artifactId",
          "artifactRevision", "modelProfile", "modelProfileVersion",
          "outputSchema", "outputSchemaVersion", "budgetJson", "resolvedModelJson", "usageJson",
          "lastProgressSequence", "submittedAt", "updatedAt", "completedAt"
        ) VALUES (
          'step-1', 'v2-run', 'agent', 'completed', 1, 'review_candidate', 'creative',
          1, 1, 'step-request-1', repeat('d', 64), repeat('e', 64), repeat('f', 64),
          'bundle-1', 'artifact-1', 1, 'reviewer', 'profile-v1',
          'output.chapter_review_report.v1', '1', '{}',
          '{"deploymentFingerprint":"deployment-v1"}',
          '{"usageStatus":"complete","providerAttempts":1}', 2,
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        INSERT INTO "WorkflowEvent" (
          id, "runId", sequence, "eventType", "payloadJson", "dedupeKey"
        ) VALUES (
          'event-step-finished', 'v2-run', 2, 'step_finished',
          '{"stepId":"step-1","fencingToken":1,"status":"completed","errorCode":null}',
          'step:finished:step-1:1'
        );
        UPDATE "WorkflowRun" SET "lastEventSequence" = 2 WHERE id = 'v2-run';
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-1', 'v2-run', 'step-1', 'bundle-1', 'artifact-1', 1,
          'reviewer', 'rubric-v1', 'completed', 'pass', '[]'
        );
        INSERT INTO "WorkflowBillingReservation" (
          id, "runId", "stepId", "userId", "requestId", "pricingVersion",
          "pricingJson", "reservedMicros", "chargedMicros", "usageJson", status,
          "updatedAt", "settledAt"
        ) VALUES (
          'billing-1', 'v2-run', 'step-1', 'migration-user', 'billing-request-1',
          'credit-pricing.v1',
          '{"provider":"openai_compatible","model":"deepseek-v4-flash"}',
          1000, 500, '{"usageStatus":"complete","providerAttempts":1}',
          'settled', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        COMMIT;
        """,
    )
    assert _scalar(
        docker,
        container,
        'SELECT count(*) FROM "WorkflowEvaluation" WHERE "runId" = \'v2-run\';',
    ) == "1"
    assert _scalar(
        docker,
        container,
        'SELECT count(*) FROM "WorkflowBillingReservation" '
        'WHERE "runId" = \'v2-run\' AND status = \'settled\';',
    ) == "1"

    immutable_billing_identity = _psql(
        docker,
        container,
        """
        UPDATE "WorkflowBillingReservation"
        SET "reservedMicros" = 1001
        WHERE id = 'billing-1';
        """,
        check=False,
    )
    assert immutable_billing_identity.returncode != 0
    assert "身份、价格与预留上限不可修改" in immutable_billing_identity.stderr

    invalid_billing_status = _psql(
        docker,
        container,
        """
        UPDATE "WorkflowBillingReservation"
        SET status = 'released', "chargedMicros" = 500
        WHERE id = 'billing-1';
        """,
        check=False,
    )
    assert invalid_billing_status.returncode != 0
    assert "WorkflowBillingReservation_status_shape_check" in invalid_billing_status.stderr

    invalid_run_cancel_shapes = (
        """
        UPDATE "WorkflowRun"
        SET "cancelRequestId" = 'cancel-1'
        WHERE id = 'v2-run';
        """,
        """
        UPDATE "WorkflowRun"
        SET "cancelRequestedAt" = CURRENT_TIMESTAMP
        WHERE id = 'v2-run';
        """,
    )
    for statement in invalid_run_cancel_shapes:
        invalid_cancel_shape = _psql(docker, container, statement, check=False)
        assert invalid_cancel_shape.returncode != 0
        assert "WorkflowRun_cancel_binding_check" in invalid_cancel_shape.stderr

    invalid_step_snapshots = (
        (
            'UPDATE "WorkflowStep" SET "resolvedModelJson" = \'[]\' '
            "WHERE id = 'step-1';",
            "V2 WorkflowStep 的 resolved model 只能从 NULL 冻结一次",
        ),
        (
            'UPDATE "WorkflowStep" SET "usageJson" = \'[]\' '
            "WHERE id = 'step-1';",
            "WorkflowStep_usageJson_check",
        ),
        (
            'UPDATE "WorkflowStep" SET "lastProgressSequence" = -1 '
            "WHERE id = 'step-1';",
            "WorkflowStep_progress_sequence_check",
        ),
        (
            'UPDATE "WorkflowStep" SET "usageJson" = NULL '
            "WHERE id = 'step-1';",
            "WorkflowStep_progress_sequence_check",
        ),
    )
    for statement, constraint_name in invalid_step_snapshots:
        invalid_step_snapshot = _psql(docker, container, statement, check=False)
        assert invalid_step_snapshot.returncode != 0
        assert constraint_name in invalid_step_snapshot.stderr

    _psql(
        docker,
        container,
        """
        UPDATE "WorkflowRun"
        SET "cancelRequestId" = 'cancel-1', "cancelRequestedAt" = CURRENT_TIMESTAMP
        WHERE id = 'v2-run';
        """,
    )
    mismatched_step_cancel = _psql(
        docker,
        container,
        """
        UPDATE "WorkflowStep"
        SET "cancelRequestId" = 'cancel-other'
        WHERE id = 'step-1';
        """,
        check=False,
    )
    assert mismatched_step_cancel.returncode != 0
    assert "WorkflowStep_cancel_run_fkey" in mismatched_step_cancel.stderr
    _psql(
        docker,
        container,
        """
        UPDATE "WorkflowStep"
        SET "cancelRequestId" = 'cancel-1'
        WHERE id = 'step-1';
        """,
    )
    cancel_identity_mutations = (
        (
            'UPDATE "WorkflowRun" SET "cancelRequestId" = \'cancel-2\' '
            "WHERE id = 'v2-run';",
            "V2 WorkflowRun 的取消身份只能从 NULL 冻结一次",
        ),
        (
            'UPDATE "WorkflowRun" SET "cancelRequestedAt" = '
            '"cancelRequestedAt" + interval \'1 second\' '
            "WHERE id = 'v2-run';",
            "V2 WorkflowRun 的取消身份只能从 NULL 冻结一次",
        ),
        (
            'UPDATE "WorkflowStep" SET "cancelRequestId" = NULL '
            "WHERE id = 'step-1';",
            "V2 WorkflowStep 的取消身份只能从 NULL 冻结一次",
        ),
    )
    for statement, message in cancel_identity_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert message in refused.stderr

    duplicate_foreground_run = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "writingSessionId", "idempotencyKey", "requestHash", "budgetJson",
          "modelPolicyJson", "lastEventSequence", revision
        ) VALUES (
          'duplicate-foreground', 'migration-novel', 'migration-chapter',
          'migration-user', 'chat', 'pending', CURRENT_TIMESTAMP, 2,
          'long_serial', 'answer_question', 'catalog-v1', 'migration-session',
          'duplicate-foreground-request', repeat('0', 64), '{}', '{}', 0, 1
        );
        """,
        check=False,
    )
    assert duplicate_foreground_run.returncode != 0
    assert "WorkflowRun_v2_writingSession_foreground_key" in duplicate_foreground_run.stderr

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "writingSessionId", "idempotencyKey", "requestHash", "budgetJson",
          "modelPolicyJson", "lastEventSequence", revision, "completedAt"
        ) VALUES (
          'completed-foreground', 'migration-novel', 'migration-chapter',
          'migration-user', 'chat', 'completed', CURRENT_TIMESTAMP, 2,
          'long_serial', 'answer_question', 'catalog-v1', 'migration-session',
          'completed-foreground-request', repeat('0', 64), '{}', '{}', 0, 1,
          CURRENT_TIMESTAMP
        );
        """,
    )

    invalid_item = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvidenceItem" (
          id, "bundleId", ordinal, "resourceType", "resourceId", exists,
          "contentType", "contentText", "contentJson", "contentSha256", "byteCount"
        ) VALUES (
          'item-invalid', 'bundle-1', 3, 'chapter', 'chapter-1', TRUE,
          'text', 'text', '{}', repeat('1', 64), 4
        );
        """,
        check=False,
    )
    assert invalid_item.returncode != 0
    assert "WorkflowEvidenceItem_content_exclusive_check" in invalid_item.stderr

    invalid_absence = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvidenceItem" (
          id, "bundleId", ordinal, "resourceType", "resourceId", exists,
          "resourceRevision", "byteCount"
        ) VALUES (
          'item-invalid-absence', 'bundle-1', 3, 'beat_plan', 'missing-plan',
          FALSE, 1, 0
        );
        """,
        check=False,
    )
    assert invalid_absence.returncode != 0
    assert "WorkflowEvidenceItem_existence_shape_check" in invalid_absence.stderr

    pending_without_due_time = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status, ordinal, purpose, lane,
          "attemptCount", "fencingToken", "idempotencyKey", "requestHash",
          "inputHash", "submittedAt", "updatedAt"
        ) VALUES (
          'step-no-due', 'v2-run', 'agent', 'pending', 2, 'generation', 'creative',
          0, 0, 'step-no-due-request', repeat('2', 64), repeat('3', 64),
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """,
        check=False,
    )
    assert pending_without_due_time.returncode != 0
    assert "WorkflowStep_v2_shape_check" in pending_without_due_time.stderr

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status, ordinal, purpose, lane,
          "attemptCount", "fencingToken", "idempotencyKey", "requestHash",
          "inputHash", "resultHash", "evidenceBundleId", "modelProfile",
          "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson",
          "submittedAt", "updatedAt", "completedAt"
        ) VALUES (
          'step-quality', 'v2-run', 'agent', 'completed', 10, 'quality_evaluation',
          'interactive', 1, 1, 'step-quality-request', repeat('a', 64),
          repeat('b', 64), repeat('c', 64), 'bundle-1', 'quality-reviewer',
          'profile-v1', 'output.chapter_review_report.v1', '1', '{}',
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP
        );
        """,
    )
    invalid_evaluation_artifact_pairs = (
        """
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-only-artifact', 'v2-run', 'step-quality', 'bundle-1',
          'artifact-1', NULL, 'quality-reviewer', 'rubric-v1',
          'completed', 'pass', '[]'
        );
        """,
        """
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-only-revision', 'v2-run', 'step-quality', 'bundle-1',
          NULL, 1, 'quality-reviewer', 'rubric-v1',
          'completed', 'pass', '[]'
        );
        """,
    )
    for statement in invalid_evaluation_artifact_pairs:
        invalid_artifact_pair = _psql(
            docker,
            container,
            statement,
            check=False,
        )
        assert invalid_artifact_pair.returncode != 0
        assert "WorkflowEvaluation_artifact_binding_check" in invalid_artifact_pair.stderr

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-quality', 'v2-run', 'step-quality', 'bundle-1', NULL, NULL,
          'quality-reviewer', 'rubric-v1', 'completed', 'pass', '[]'
        );
        """,
    )
    assert _scalar(
        docker,
        container,
        """
        SELECT ("artifactId" IS NULL AND "artifactRevision" IS NULL)::text
        FROM "WorkflowEvaluation" WHERE id = 'evaluation-quality';
        """,
    ) == "true"

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt",
          "engineVersion", workflow, operation, "operationCatalogVersion",
          "idempotencyKey", "requestHash", "budgetJson", "modelPolicyJson",
          "lastEventSequence", revision
        ) VALUES (
          'v2-run-b', 'migration-novel', 'migration-chapter', 'migration-user',
          'chat', 'running', CURRENT_TIMESTAMP, 2, 'long_serial', 'review_chapter',
          'catalog-v1', 'request-b', repeat('6', 64), '{}', '{}', 0, 1
        );
        INSERT INTO "ReviewArtifact" (
          id, "novelId", "workflowRunId", kind, status, "payloadJson", "updatedAt"
        ) VALUES (
          'artifact-b', 'migration-novel', 'v2-run-b', 'chapter_content',
          'under_review', '{}', CURRENT_TIMESTAMP
        );
        INSERT INTO "ReviewArtifactRevision" (
          id, "artifactId", revision, "payloadJson"
        ) VALUES ('artifact-revision-b', 'artifact-b', 1, '{}');
        """,
    )

    cross_novel_artifact = _psql(
        docker,
        container,
        """
        INSERT INTO "ReviewArtifact" (
          id, "novelId", "workflowRunId", kind, status, "payloadJson", "updatedAt"
        ) VALUES (
          'artifact-cross-novel', 'other-novel', 'v2-run', 'chapter_content',
          'under_review', '{}', CURRENT_TIMESTAMP
        );
        """,
        check=False,
    )
    assert cross_novel_artifact.returncode != 0
    assert "ReviewArtifact_workflow_run_novel_fkey" in cross_novel_artifact.stderr

    cross_run_step = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status, ordinal, purpose, lane,
          "attemptCount", "fencingToken", "idempotencyKey", "requestHash",
          "inputHash", "resultHash", "evidenceBundleId", "artifactId",
          "artifactRevision", "modelProfile", "modelProfileVersion",
          "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt",
          "completedAt"
        ) VALUES (
          'step-cross-run', 'v2-run', 'agent', 'completed', 2, 'review_candidate',
          'interactive', 1, 1, 'step-cross-run-request', repeat('7', 64),
          repeat('8', 64), repeat('9', 64), 'bundle-1', 'artifact-b', 1,
          'reviewer', 'profile-v1', 'output.chapter_review_report.v1', '1', '{}', CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """,
        check=False,
    )
    assert cross_run_step.returncode != 0
    assert "WorkflowStep_artifact_run_fkey" in cross_run_step.stderr

    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowStep" (
          id, "runId", "stepType", status, ordinal, purpose, lane,
          "attemptCount", "fencingToken", "idempotencyKey", "requestHash",
          "inputHash", "resultHash", "evidenceBundleId", "artifactId",
          "artifactRevision", "modelProfile", "modelProfileVersion",
          "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt",
          "completedAt"
        ) VALUES (
          'step-2', 'v2-run', 'agent', 'completed', 2, 'review_candidate',
          'interactive', 1, 1, 'step-request-2', repeat('7', 64),
          repeat('8', 64), repeat('9', 64), 'bundle-1', 'artifact-1', 1,
          'reviewer', 'profile-v1', 'output.chapter_review_report.v1', '1', '{}', CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """,
    )
    cross_run_evaluation = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-cross-run', 'v2-run', 'step-2', 'bundle-1', 'artifact-b', 1,
          'reviewer', 'rubric-v1', 'completed', 'pass', '[]'
        );
        """,
        check=False,
    )
    assert cross_run_evaluation.returncode != 0
    assert "WorkflowEvaluation_step_exact_fkey" in cross_run_evaluation.stderr

    invalid_evaluation = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvaluation" (
          id, "runId", "stepId", "evidenceBundleId", "artifactId",
          "artifactRevision", "evaluatorProfile", "rubricVersion",
          "executionStatus", "contentVerdict", "findingsJson"
        ) VALUES (
          'evaluation-invalid-content', 'v2-run', 'step-2', 'bundle-1',
          'artifact-1', 1, 'reviewer', 'rubric-v1', 'failed', 'pass', '[]'
        );
        """,
        check=False,
    )
    assert invalid_evaluation.returncode != 0
    assert "WorkflowEvaluation_execution_content_check" in invalid_evaluation.stderr

    duplicate_event = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvent" (
          id, "runId", sequence, "eventType", "payloadJson", "dedupeKey"
        ) VALUES ('event-duplicate', 'v2-run', 1, 'step_started', '{}', 'started');
        """,
        check=False,
    )
    assert duplicate_event.returncode != 0
    assert "WorkflowEvent_run_sequence_key" in duplicate_event.stderr

    invalid_event_type = _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowEvent" (
          id, "runId", sequence, "eventType", "payloadJson", "dedupeKey"
        ) VALUES ('event-invalid-type', 'v2-run', 3, 'agent_done', '{}', 'invalid-type');
        """,
        check=False,
    )
    assert invalid_event_type.returncode != 0
    assert "WorkflowEvent_eventType_check" in invalid_event_type.stderr

    immutable_statements = (
        'UPDATE "WorkflowEvidenceBundle" SET "totalBytes" = 4 WHERE id = \'bundle-1\';',
        'DELETE FROM "WorkflowEvidenceItem" WHERE id = \'item-1\';',
        'UPDATE "WorkflowEvent" SET "payloadJson" = \'{"changed":true}\' '
        "WHERE id = 'event-1';",
        'DELETE FROM "WorkflowEvaluation" WHERE id = \'evaluation-1\';',
    )
    for statement in immutable_statements:
        immutable_mutation = _psql(docker, container, statement, check=False)
        assert immutable_mutation.returncode != 0
        assert "不可变工作流审计事实" in immutable_mutation.stderr

    run_identity_mutations = (
        'UPDATE "WorkflowRun" SET "requestHash" = repeat(\'0\', 64) '
        "WHERE id = 'v2-run';",
        'UPDATE "WorkflowRun" SET "targetId" = \'changed-target\' '
        "WHERE id = 'v2-run';",
        'UPDATE "WorkflowRun" SET "budgetJson" = \'{\"changed\":true}\' '
        "WHERE id = 'v2-run';",
        'UPDATE "WorkflowRun" SET "modelPolicyJson" = \'{\"changed\":true}\' '
        "WHERE id = 'v2-run';",
    )
    for statement in run_identity_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert "执行计划身份不可修改" in refused.stderr

    step_identity_mutations = (
        'UPDATE "WorkflowStep" SET input = \'{\"changed\":true}\' '
        "WHERE id = 'step-1';",
        'UPDATE "WorkflowStep" SET "modelProfile" = \'other-profile\' '
        "WHERE id = 'step-1';",
        'UPDATE "WorkflowStep" SET "outputSchema" = \'output.other.v1\' '
        "WHERE id = 'step-1';",
        'UPDATE "WorkflowStep" SET "budgetJson" = \'{\"changed\":true}\' '
        "WHERE id = 'step-1';",
    )
    for statement in step_identity_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert "调用身份不可修改" in refused.stderr

    # 合法生命周期字段可更新；resolved/result/artifact 只允许从 NULL 一次冻结。
    _psql(
        docker,
        container,
        """
        INSERT INTO "WorkflowStep" (
          id, "runId", "agentId", "stepType", status, input, "createdAt",
          ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
          "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
          "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion",
          "budgetJson", "submittedAt", "updatedAt"
        ) VALUES (
          'step-freeze', 'v2-run', 'writer', 'agent', 'pending', '{}', CURRENT_TIMESTAMP,
          30, 'generation', 'creative', 0, CURRENT_TIMESTAMP, 0,
          'step-freeze-request', repeat('1', 64), repeat('2', 64), 'bundle-1',
          'writer', 'profile-v1', 'output.chapter_review_report.v1', '1', '{}',
          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        UPDATE "WorkflowStep"
        SET status = 'running', "attemptCount" = 1, "fencingToken" = 1,
            "activeJobId" = 'job-freeze',
            "leaseExpiresAt" = CURRENT_TIMESTAMP + interval '30 seconds',
            "heartbeatAt" = CURRENT_TIMESTAMP,
            "resolvedModelJson" = '{"deploymentFingerprint":"frozen-v1"}',
            "usageJson" = '{"usageStatus":"unknown","providerAttempts":0}',
            "lastProgressSequence" = 1, "updatedAt" = CURRENT_TIMESTAMP
        WHERE id = 'step-freeze';
        UPDATE "WorkflowStep"
        SET status = 'completed', "resultHash" = repeat('3', 64),
            "artifactId" = 'artifact-1', "artifactRevision" = 1,
            "activeJobId" = NULL, "leaseExpiresAt" = NULL,
            "completedAt" = CURRENT_TIMESTAMP, "errorCode" = 'terminal-code',
            "updatedAt" = CURRENT_TIMESTAMP
        WHERE id = 'step-freeze';
        UPDATE "WorkflowRun"
        SET status = 'waiting_user', "lastEventSequence" = "lastEventSequence" + 1,
            revision = revision + 1, "updatedAt" = CURRENT_TIMESTAMP
        WHERE id = 'v2-run';
        UPDATE "WorkflowRun" SET input = '{"v1Allowed":true}' WHERE id = 'legacy-run';
        UPDATE "WorkflowStep" SET input = '{"v1Allowed":true}'
        WHERE "runId" = 'legacy-run';
        INSERT INTO "WorkflowRun" (
          id, "novelId", "chapterId", "userId", kind, status, "updatedAt"
        ) VALUES (
          'legacy-delete-run', 'migration-novel', 'migration-chapter',
          'migration-user', 'chat', 'completed', CURRENT_TIMESTAMP
        );
        INSERT INTO "WorkflowStep" (id, "runId", "stepType", status)
        VALUES ('legacy-delete-step', 'legacy-delete-run', 'tool', 'completed');
        DELETE FROM "WorkflowStep" WHERE id = 'legacy-delete-step';
        DELETE FROM "WorkflowRun" WHERE id = 'legacy-delete-run';
        """,
    )
    one_time_freeze_mutations = (
        'UPDATE "WorkflowStep" SET "resolvedModelJson" = \'{\"changed\":true}\' '
        "WHERE id = 'step-freeze';",
        'UPDATE "WorkflowStep" SET "resultHash" = repeat(\'4\', 64) '
        "WHERE id = 'step-freeze';",
        'UPDATE "WorkflowStep" SET "artifactRevision" = 2 '
        "WHERE id = 'step-freeze';",
    )
    for statement in one_time_freeze_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert "只能从 NULL 冻结一次" in refused.stderr

    terminal_step_mutations = (
        (
            'UPDATE "WorkflowStep" SET status = \'running\', "completedAt" = NULL '
            "WHERE id = 'step-freeze';",
            "V2 WorkflowStep 的终态不可反转",
        ),
        (
            'UPDATE "WorkflowStep" SET "completedAt" = '
            '"completedAt" + interval \'1 second\' '
            "WHERE id = 'step-freeze';",
            "V2 WorkflowStep 的完成时间与错误码只能从 NULL 冻结一次",
        ),
        (
            'UPDATE "WorkflowStep" SET "errorCode" = \'changed-code\' '
            "WHERE id = 'step-freeze';",
            "V2 WorkflowStep 的完成时间与错误码只能从 NULL 冻结一次",
        ),
    )
    for statement, message in terminal_step_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert message in refused.stderr

    _psql(
        docker,
        container,
        """
        UPDATE "WorkflowRun"
        SET status = 'failed', "completedAt" = CURRENT_TIMESTAMP,
            "errorCode" = 'terminal-code', "updatedAt" = CURRENT_TIMESTAMP
        WHERE id = 'style-run';
        """,
    )
    terminal_run_mutations = (
        (
            'UPDATE "WorkflowRun" SET status = \'running\', "completedAt" = NULL '
            "WHERE id = 'style-run';",
            "V2 WorkflowRun 的终态不可反转",
        ),
        (
            'UPDATE "WorkflowRun" SET "completedAt" = '
            '"completedAt" + interval \'1 second\' '
            "WHERE id = 'style-run';",
            "V2 WorkflowRun 的完成时间与错误码只能从 NULL 冻结一次",
        ),
        (
            'UPDATE "WorkflowRun" SET "errorCode" = \'changed-code\' '
            "WHERE id = 'style-run';",
            "V2 WorkflowRun 的完成时间与错误码只能从 NULL 冻结一次",
        ),
    )
    for statement, message in terminal_run_mutations:
        refused = _psql(docker, container, statement, check=False)
        assert refused.returncode != 0
        assert message in refused.stderr

    refused_step_delete = _psql(
        docker,
        container,
        'DELETE FROM "WorkflowStep" WHERE id = \'step-freeze\';',
        check=False,
    )
    assert refused_step_delete.returncode != 0
    assert "V2 WorkflowStep 是不可删除的耐久执行审计事实" in refused_step_delete.stderr

    refused_rollback = _psql(docker, container, rollback, check=False)
    assert refused_rollback.returncode != 0
    assert "engineVersion=2" in refused_rollback.stderr
    assert _scalar(
        docker,
        container,
        'SELECT "engineVersion" FROM "WorkflowRun" WHERE id = \'v2-run\';',
    ) == "2"

    retained_artifact = _psql(
        docker,
        container,
        """
        DELETE FROM "WorkflowRun" WHERE id = 'v2-run';
        """,
        check=False,
    )
    assert retained_artifact.returncode != 0
    assert "V2 WorkflowRun 是不可删除的耐久执行审计事实" in retained_artifact.stderr

    # 管理员级故障注入制造“Run 已丢失但 Artifact 仍保留旧 runId”的孤儿事实；
    # rollback 必须明确拒绝，而不能把它误判成空 V2。
    _psql(
        docker,
        container,
        """
        SET session_replication_role = replica;
        UPDATE "ReviewArtifact"
        SET "workflowRunId" = 'missing-v2-run'
        WHERE id = 'artifact-1';
        DELETE FROM "WorkflowBillingReservation";
        DELETE FROM "WorkflowEvaluation";
        DELETE FROM "WorkflowEvent";
        DELETE FROM "WorkflowStep" WHERE ordinal IS NOT NULL;
        DELETE FROM "WorkflowEvidenceItem";
        DELETE FROM "WorkflowEvidenceBundle";
        DELETE FROM "ReviewArtifactRevision" WHERE "artifactId" = 'artifact-b';
        DELETE FROM "ReviewArtifact" WHERE id = 'artifact-b';
        DELETE FROM "WorkflowRun" WHERE "engineVersion" = 2;
        SET session_replication_role = origin;
        """,
    )

    orphan_rollback = _psql(docker, container, rollback, check=False)
    assert orphan_rollback.returncode != 0
    assert "孤儿 ReviewArtifact" in orphan_rollback.stderr

    _psql(
        docker,
        container,
        """
        DELETE FROM "ReviewArtifactRevision" WHERE "artifactId" = 'artifact-1';
        DELETE FROM "ReviewArtifact" WHERE id = 'artifact-1';
        """,
    )

    _psql(docker, container, rollback)
    _psql(docker, container, rollback)
    assert _scalar(
        docker,
        container,
        """
        SELECT (
          to_regclass('public."WorkflowEvidenceBundle"') IS NULL
          AND to_regclass('public."WorkflowEvent"') IS NULL
          AND to_regclass('public."WorkflowBillingReservation"') IS NULL
          AND to_regprocedure('public."rejectWorkflowAuditMutation"()') IS NULL
          AND to_regprocedure('public."rejectWorkflowBillingIdentityMutation"()') IS NULL
          AND to_regprocedure('public."rejectWorkflowRunV2IdentityMutation"()') IS NULL
          AND to_regprocedure('public."rejectWorkflowStepV2IdentityMutation"()') IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'WorkflowRun'
              AND column_name = 'engineVersion'
          )
        )::text;
        """,
    ) == "true"
    assert _scalar(
        docker,
        container,
        """
        SELECT count(*)
        FROM "WorkflowRun" AS run
        JOIN "WorkflowStep" AS step ON step."runId" = run.id
        WHERE run.id = 'legacy-run';
        """,
    ) == "1"

    _psql(docker, container, forward)
    assert _scalar(
        docker,
        container,
        """
        SELECT (
          to_regclass('public."WorkflowEvidenceBundle"') IS NOT NULL
          AND to_regclass('public."WorkflowEvidenceItem"') IS NOT NULL
          AND to_regclass('public."WorkflowEvent"') IS NOT NULL
          AND to_regclass('public."WorkflowEvaluation"') IS NOT NULL
          AND to_regclass('public."WorkflowBillingReservation"') IS NOT NULL
        )::text;
        """,
    ) == "true"

    # 同名但错误的列、CHECK 与索引必须让幂等重跑失败，不能只凭名字宣告成功。
    _psql(
        docker,
        container,
        """
        ALTER TABLE "WorkflowRun"
          DROP CONSTRAINT "WorkflowRun_v1_scope_check";
        ALTER TABLE "WorkflowRun"
          ADD CONSTRAINT "WorkflowRun_v1_scope_check" CHECK (TRUE);
        ALTER TABLE "WorkflowRun"
          ALTER COLUMN "errorCode" TYPE VARCHAR(255);
        ALTER TABLE "WorkflowStep"
          ALTER COLUMN "resolvedModelJson" TYPE VARCHAR(255);
        ALTER TABLE "WorkflowStep"
          DROP CONSTRAINT "WorkflowStep_progress_sequence_check";
        ALTER TABLE "WorkflowStep"
          ADD CONSTRAINT "WorkflowStep_progress_sequence_check" CHECK (TRUE);
        DROP INDEX "WorkflowStep_due_idx";
        CREATE INDEX "WorkflowStep_due_idx" ON "WorkflowStep"(id);
        DROP INDEX "WorkflowRun_v2_writingSession_foreground_key";
        CREATE UNIQUE INDEX "WorkflowRun_v2_writingSession_foreground_key"
          ON "WorkflowRun"(id);
        """,
    )
    drifted_reforward = _psql(docker, container, forward, check=False)
    assert drifted_reforward.returncode != 0
    assert "WorkflowRun.errorCode:type_or_nullability" in drifted_reforward.stderr
    assert "WorkflowRun.WorkflowRun_v1_scope_check:definition" in drifted_reforward.stderr
    assert "WorkflowStep.resolvedModelJson:type_or_nullability" in drifted_reforward.stderr
    assert (
        "WorkflowStep.WorkflowStep_progress_sequence_check:definition"
        in drifted_reforward.stderr
    )
    assert "WorkflowStep_due_idx:definition" in drifted_reforward.stderr
    assert (
        "WorkflowRun_v2_writingSession_foreground_key:definition"
        in drifted_reforward.stderr
    )
