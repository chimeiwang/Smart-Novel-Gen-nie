from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION_PATH = ROOT / "scripts" / "migrations" / "20260801_writing_event_outbox.sql"


def _migration() -> str:
    return MIGRATION_PATH.read_text("utf-8")


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_outbox_migration_is_single_transaction_and_rerun_safe() -> None:
    sql = _migration()
    compact = _compact(sql)

    assert compact.startswith("BEGIN;")
    assert compact.endswith("COMMIT;")
    assert "pg_advisory_xact_lock" in sql
    assert "to_regclass('public.\"WritingEventOutbox\"')" in sql
    assert 'CREATE TABLE "WritingEventOutbox"' in sql
    assert 'CREATE INDEX IF NOT EXISTS "WritingEventOutbox_due_idx"' in sql
    assert "pg_get_constraintdef" in sql
    assert "RAISE EXCEPTION" in sql
    assert "DROP TABLE" not in sql.upper()


def test_outbox_migration_declares_all_columns_and_references() -> None:
    sql = _migration()

    required_columns = {
        "id",
        "taskId",
        "commandId",
        "sourceEventId",
        "sourceSequence",
        "durableBaseline",
        "dedupeKey",
        "eventType",
        "payloadJson",
        "deliveryState",
        "attemptCount",
        "nextAttemptAt",
        "leaseToken",
        "leaseExpiresAt",
        "lastErrorCode",
        "redisEventId",
        "createdAt",
        "updatedAt",
        "publishedAt",
    }
    declared_columns = set(
        re.findall(r'^\s+"([A-Za-z][A-Za-z0-9]*)"\s+', sql, flags=re.MULTILINE)
    )

    assert required_columns <= declared_columns
    assert 'REFERENCES "WritingTask"("id")' in sql
    assert "ON DELETE CASCADE ON UPDATE CASCADE" in sql
    assert 'REFERENCES "WritingRunCommand"("id")' in sql
    assert "ON DELETE SET NULL ON UPDATE CASCADE" in sql


def test_outbox_migration_enforces_domain_and_lease_invariants() -> None:
    compact = _compact(_migration())

    assert all(
        value in compact
        for value in ("pending", "delivering", "published", "blocked", "superseded")
    )
    assert all(
        value in compact
        for value in ("completed", "error", "artifact_awaiting_user_approval")
    )
    assert '"sourceSequence" > 0' in compact
    assert '"durableBaseline" >= 0' in compact
    assert '"durableBaseline" < "sourceSequence"' in compact
    assert '"attemptCount" >= 0' in compact
    assert 'jsonb_typeof("payloadJson"::jsonb) = \'object\'' in compact
    assert '"deliveryState" = \'delivering\'' in compact
    assert '"leaseToken" IS NOT NULL' in compact
    assert '"leaseExpiresAt" IS NOT NULL' in compact
    assert '"deliveryState" = \'published\'' in compact
    assert '"redisEventId" IS NOT NULL' in compact
    assert '"publishedAt" IS NOT NULL' in compact


def test_outbox_migration_creates_ordering_delivery_and_cleanup_indexes() -> None:
    compact = _compact(_migration())

    assert (
        'CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_sourceEventId_key" '
        'ON "WritingEventOutbox"("sourceEventId")' in compact
    )
    assert (
        'CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_dedupeKey_key" '
        'ON "WritingEventOutbox"("dedupeKey")' in compact
    )
    assert (
        'CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_taskId_sourceSequence_key" '
        'ON "WritingEventOutbox"("taskId", "sourceSequence")' in compact
    )
    assert (
        'CREATE INDEX IF NOT EXISTS "WritingEventOutbox_due_idx" '
        'ON "WritingEventOutbox"("deliveryState", "nextAttemptAt", "createdAt") '
        "WHERE \"deliveryState\" IN ('pending', 'delivering')" in compact
    )
    assert (
        'CREATE INDEX IF NOT EXISTS "WritingEventOutbox_task_sequence_idx" '
        'ON "WritingEventOutbox"("taskId", "sourceSequence")' in compact
    )
    assert (
        'CREATE INDEX IF NOT EXISTS "WritingEventOutbox_publishedAt_idx" '
        'ON "WritingEventOutbox"("publishedAt") WHERE "publishedAt" IS NOT NULL'
        in compact
    )


def test_outbox_migration_documents_table_and_operational_fields_in_chinese() -> None:
    sql = _migration()

    assert "COMMENT ON TABLE \"WritingEventOutbox\" IS '写作边界事件事务发件箱'" in sql
    assert "业务事实" in sql
    assert "投递租约" in sql
    assert "Redis Stream" in sql


def test_outbox_plan_points_readiness_work_to_existing_health_test() -> None:
    plan = (
        ROOT / "docs" / "plans" / "2026-08-01-writing-run-state-machine-and-outbox.md"
    ).read_text("utf-8")

    assert "apps/core-api/tests/test_health.py" in plan
    assert "apps/core-api/tests/test_app.py" not in plan
