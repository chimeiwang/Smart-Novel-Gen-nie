from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION_PATH = (
    ROOT / "scripts" / "migrations" / "20260821_token_usage_task_run.sql"
)


def _migration() -> str:
    return MIGRATION_PATH.read_text("utf-8")


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_token_usage_migration_is_transactional_additive_and_rerun_safe() -> None:
    sql = _migration()
    compact = _compact(sql)

    assert compact.startswith("begin;")
    assert compact.endswith("commit;")
    assert "set local search_path = pg_catalog, public" in compact
    assert "pg_advisory_xact_lock" in compact
    assert (
        'alter table "tokenusage" add column if not exists "requestid" text'
        in compact
    )
    assert 'alter table "tokenusage" add column if not exists "taskid" text' in compact
    assert 'alter table "tokenusage" add column if not exists "runid" text' in compact
    assert "drop table" not in compact
    assert "drop column" not in compact
    assert "delete from" not in compact
    assert "update \"tokenusage\"" not in compact


def test_token_usage_migration_declares_request_constraint_and_exact_indexes() -> None:
    compact = _compact(_migration())

    assert 'constraint "tokenusage_requestid_check"' in compact
    assert '"requestid" is null or btrim("requestid") <> \'\'' in compact
    assert "not valid" in compact
    assert (
        'validate constraint "tokenusage_requestid_check"'
        in compact
    )
    assert (
        'create unique index if not exists "tokenusage_requestid_key" '
        'on "tokenusage"("requestid")' in compact
    )
    assert (
        'create index if not exists "tokenusage_userid_taskid_createdat_idx" '
        'on "tokenusage"("userid", "taskid", "createdat")' in compact
    )
    assert (
        'create index if not exists "tokenusage_runid_createdat_idx" '
        'on "tokenusage"("runid", "createdat")' in compact
    )


def test_token_usage_migration_self_verifies_columns_constraint_and_indexes() -> None:
    compact = _compact(_migration())

    assert "do $verification$" in compact
    assert "to_regclass('public.\"tokenusage\"')" in compact
    assert "pg_attribute" in compact
    assert "format_type" in compact
    assert "not attribute.attnotnull" in compact
    assert "not attribute.atthasdef" in compact
    assert "attribute.attidentity = ''" in compact
    assert "attribute.attgenerated = ''" in compact
    assert all(name in compact for name in ("requestid", "taskid", "runid"))
    assert "pg_get_constraintdef" in compact
    assert "constraint_definition.convalidated" in compact
    assert "regexp_replace" in compact
    assert (
        "request_constraint is distinct from "
        "'check(((\"requestid\"isnull)or(btrim(\"requestid\")<>''''::text)))'"
        in compact
    )
    assert "position('btrim' in request_constraint)" not in compact
    assert "position('requestid' in request_constraint)" not in compact
    assert "pg_index" in compact
    assert "index_definition.indisvalid" in compact
    assert "index_definition.indisready" in compact
    assert "index_definition.indisunique" in compact
    assert "index_definition.indnatts = index_definition.indnkeyatts" in compact
    assert "unnest(index_definition.indoption)" in compact
    assert "pg_opclass" in compact
    assert "operator_class.opcdefault" in compact
    assert "pg_catalog.text_ops" in compact
    assert "pg_catalog.timestamp_ops" in compact
    assert "pg_collation" in compact
    assert "pg_catalog.default" in compact
    assert "index_relation.reloptions is null" in compact
    assert "index_relation.reltablespace = 0" in compact
    assert all(
        name in compact
        for name in (
            "tokenusage_requestid_key",
            "tokenusage_userid_taskid_createdat_idx",
            "tokenusage_runid_createdat_idx",
        )
    )
    assert "raise exception" in compact
