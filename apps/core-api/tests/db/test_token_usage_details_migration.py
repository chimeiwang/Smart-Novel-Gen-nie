from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION_PATH = ROOT / "scripts" / "migrations" / "20260823_token_usage_details.sql"


def _migration() -> str:
    return MIGRATION_PATH.read_text("utf-8")


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_token_usage_details_migration_is_additive_nullable_and_rerun_safe() -> None:
    compact = _compact(_migration())

    assert compact.startswith("begin;")
    assert compact.endswith("commit;")
    assert (
        'alter table "tokenusage" add column if not exists "promptcachemisstokens" integer'
        in compact
    )
    assert 'alter table "tokenusage" add column if not exists "reasoningtokens" integer' in compact
    assert "promptcachemisstokens" in compact
    assert "reasoningtokens" in compact
    assert "default" not in compact
    assert "update \"tokenusage\"" not in compact
    assert "insert into \"tokenusage\"" not in compact
    assert "create index" not in compact


def test_token_usage_details_migration_declares_exact_three_checks() -> None:
    compact = _compact(_migration())

    assert 'constraint "tokenusage_token_details_nonnegative_check"' in compact
    assert 'constraint "tokenusage_prompt_cache_details_check"' in compact
    assert 'constraint "tokenusage_reasoning_details_check"' in compact
    assert '"promptcachemisstokens" is null or "promptcachemisstokens" >= 0' in compact
    assert '"reasoningtokens" is null or "reasoningtokens" >= 0' in compact
    assert '"cachedtokens" + "promptcachemisstokens" = "prompttokens"' in compact
    assert '"reasoningtokens" <= "completiontokens"' in compact


def test_token_usage_details_migration_self_verifies_columns_and_constraints() -> None:
    compact = _compact(_migration())

    assert "do $verification$" in compact
    assert "pg_attribute" in compact
    assert "attribute.attnotnull" in compact
    assert "attribute.atthasdef" in compact
    assert "pg_get_constraintdef" in compact
    assert "convalidated" in compact
    assert "raise exception" in compact


def test_token_usage_details_migration_compares_normalized_constraint_definitions_exactly() -> None:
    compact = _compact(_migration())
    normalized = re.sub(r"\s+", "", compact)

    assert "regexp_replace" in compact
    assert "is distinct from" in compact
    assert "for expected_constraint in" in compact
    assert "pg_temp.token_usage_details_constraint_contract" in compact
    assert "pg_get_constraintdef" in compact
    assert "expected_constraint.definition" in compact
    assert "actual_constraint_definition" in compact
    assert "position(" not in compact

    assert 'check(("promptcachemisstokens"isnullor' in normalized
    assert '"cachedtokens"+"promptcachemisstokens"="prompttokens")' in normalized
    assert '"reasoningtokens"<="completiontokens")' in normalized
