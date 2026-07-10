from __future__ import annotations

import argparse
import copy
import json
import re
import runpy
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from inkforge_core.db import schema_guard
from inkforge_core.db.schema_guard import (
    ContractIntegrityError,
    SchemaConnectionError,
    add_contract_fingerprint,
    canonical_fingerprint,
    compare_schema_contract,
    export_schema_contract,
    inspect_schema,
    load_schema_contract,
    verify_live_schema,
    verify_live_schema_with_engine,
)


def sample_contract() -> dict[str, Any]:
    return {
        "contractVersion": 1,
        "schema": "public",
        "tables": [
            {
                "name": "Novel",
                "columns": [
                    {
                        "name": "id",
                        "formatType": "text",
                        "udtName": "text",
                        "nullable": False,
                        "default": None,
                    },
                    {
                        "name": "userId",
                        "formatType": "text",
                        "udtName": "text",
                        "nullable": True,
                        "default": None,
                    },
                ],
                "primaryKey": {
                    "name": "Novel_pkey",
                    "columns": ["id"],
                    "deferrable": False,
                    "initiallyDeferred": False,
                    "validated": True,
                },
                "foreignKeys": [
                    {
                        "name": "Novel_userId_fkey",
                        "columns": ["userId"],
                        "targetSchema": "public",
                        "targetTable": "User",
                        "targetColumns": ["id"],
                        "onUpdate": "CASCADE",
                        "onDelete": "SET NULL",
                        "matchType": "SIMPLE",
                        "deferrable": False,
                        "initiallyDeferred": False,
                        "validated": True,
                    }
                ],
                "uniqueConstraints": [
                    {
                        "name": "Novel_userId_key",
                        "columns": ["userId"],
                        "deferrable": False,
                        "initiallyDeferred": False,
                        "validated": True,
                    }
                ],
                "indexes": [
                    {
                        "name": "Novel_userId_idx",
                        "unique": False,
                        "method": "btree",
                        "keyItems": [
                            {
                                "position": 1,
                                "kind": "column",
                                "column": "userId",
                                "expression": None,
                                "opclassSchema": "pg_catalog",
                                "opclass": "text_ops",
                                "collationSchema": "pg_catalog",
                                "collation": "default",
                                "order": "ASC",
                                "nulls": "LAST",
                            }
                        ],
                        "includeColumns": [],
                        "predicate": None,
                        "valid": True,
                        "ready": True,
                        "nullsNotDistinct": False,
                        "options": [],
                        "tablespace": None,
                    }
                ],
            },
            {
                "name": "RagChunk",
                "columns": [
                    {
                        "name": "embedding",
                        "formatType": "vector",
                        "udtName": "vector",
                        "nullable": False,
                        "default": None,
                    }
                ],
                "primaryKey": None,
                "foreignKeys": [],
                "uniqueConstraints": [],
                "indexes": [],
            },
        ],
        "enums": [{"name": "ChapterStatus", "values": ["drafting", "completed"]}],
        "extensions": [
            {"name": "plpgsql", "installed": True, "version": "1.0"},
            {"name": "vector", "installed": True, "version": "0.8.1"},
        ],
        "source": {
            "product": "PostgreSQL",
            "serverVersion": "17.5",
            "serverVersionNum": 170005,
            "sourceId": "a" * 64,
        },
    }


def test_canonical_fingerprint_excludes_fingerprint_and_source_metadata() -> None:
    contract = sample_contract()
    reordered = {
        "tables": contract["tables"],
        "schema": contract["schema"],
        "extensions": contract["extensions"],
        "source": contract["source"],
        "contractVersion": contract["contractVersion"],
        "enums": contract["enums"],
        "fingerprint": "应被忽略",
    }

    first = canonical_fingerprint(contract)
    second = canonical_fingerprint(reordered)
    changed_source = copy.deepcopy(contract)
    changed_source["source"] = {
        "product": "PostgreSQL",
        "serverVersion": "17.6",
        "serverVersionNum": 170006,
        "sourceId": "b" * 64,
    }

    assert first == second
    assert canonical_fingerprint(changed_source) == first
    assert compare_schema_contract(contract, changed_source) == []
    assert len(first) == 64
    assert all(character in "0123456789abcdef" for character in first)


def test_load_contract_rejects_tampered_content(tmp_path: Path) -> None:
    path = tmp_path / "schema-contract.json"
    contract = add_contract_fingerprint(sample_contract())
    contract["tables"][0]["columns"][0]["nullable"] = True
    path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ContractIntegrityError, match="指纹"):
        load_schema_contract(path)


def test_compare_returns_stably_sorted_field_level_differences() -> None:
    expected = sample_contract()
    actual = copy.deepcopy(expected)
    actual["tables"] = [actual["tables"][1]]
    actual["tables"][0]["columns"][0]["formatType"] = "vector(1536)"
    actual["tables"][0]["columns"][0]["nullable"] = True
    actual["tables"][0]["foreignKeys"] = [
        {
            "name": "RagChunk_documentId_fkey",
            "columns": ["documentId"],
            "targetSchema": "public",
            "targetTable": "RagDocument",
            "targetColumns": ["id"],
            "onUpdate": "CASCADE",
            "onDelete": "RESTRICT",
        }
    ]
    actual["tables"][0]["indexes"] = [
        {
            "name": "RagChunk_embedding_idx",
            "unique": False,
            "method": "hnsw",
            "keyItems": [],
            "includeColumns": [],
            "predicate": None,
            "valid": True,
            "ready": True,
            "nullsNotDistinct": False,
        }
    ]
    actual["tables"].append(
        {
            "name": "Unexpected",
            "columns": [],
            "primaryKey": None,
            "foreignKeys": [],
            "uniqueConstraints": [],
            "indexes": [],
        }
    )
    actual["enums"][0]["values"] = ["drafting", "review", "completed"]

    diffs = compare_schema_contract(expected, actual)
    paths = [diff.path for diff in diffs]

    assert paths == sorted(paths)
    assert "tables.Novel" in paths
    assert "tables.RagChunk.columns.embedding.formatType" in paths
    assert "tables.RagChunk.columns.embedding.nullable" in paths
    assert "tables.RagChunk.foreignKeys.RagChunk_documentId_fkey" in paths
    assert "tables.RagChunk.indexes.RagChunk_embedding_idx" in paths
    assert "tables.Unexpected" in paths
    assert "enums.ChapterStatus.values" in paths
    assert any("vector" in diff.path.lower() or "向量" in diff.message for diff in diffs)
    assert all(diff.message for diff in diffs)


def test_compare_requires_exact_extension_version_and_presence() -> None:
    expected = sample_contract()
    actual = copy.deepcopy(expected)
    actual["extensions"][1]["version"] = "0.8.9"

    diffs = compare_schema_contract(expected, actual)
    assert [diff.path for diff in diffs] == ["extensions.vector.version"]
    assert diffs[0].expected == "0.8.1"
    assert diffs[0].actual == "0.8.9"

    actual["extensions"][1]["installed"] = False
    diffs = compare_schema_contract(expected, actual)
    assert [diff.path for diff in diffs] == [
        "extensions.vector.installed",
        "extensions.vector.version",
    ]


def test_compare_reports_index_opclass_as_single_field_drift() -> None:
    expected = sample_contract()
    expected["tables"][0]["indexes"][0]["keyItems"][0]["opclass"] = "vector_cosine_ops"
    actual = copy.deepcopy(expected)
    actual["tables"][0]["indexes"][0]["keyItems"][0]["opclass"] = "vector_l2_ops"

    diffs = compare_schema_contract(expected, actual)

    assert [diff.path for diff in diffs] == [
        "tables.Novel.indexes.Novel_userId_idx.keyItems.1.opclass"
    ]


def test_compare_reports_constraint_and_index_metadata_as_field_level_drift() -> None:
    expected = sample_contract()
    actual = copy.deepcopy(expected)
    actual["tables"][0]["primaryKey"]["deferrable"] = True
    actual["tables"][0]["foreignKeys"][0]["matchType"] = "FULL"
    actual["tables"][0]["uniqueConstraints"][0]["validated"] = False
    actual["tables"][0]["indexes"][0]["options"] = ["fillfactor=80"]
    actual["tables"][0]["indexes"][0]["tablespace"] = "fastspace"

    diffs = compare_schema_contract(expected, actual)

    assert [diff.path for diff in diffs] == [
        "tables.Novel.foreignKeys.Novel_userId_fkey.matchType",
        "tables.Novel.indexes.Novel_userId_idx.options",
        "tables.Novel.indexes.Novel_userId_idx.tablespace",
        "tables.Novel.primaryKey.deferrable",
        "tables.Novel.uniqueConstraints.Novel_userId_key.validated",
    ]


def test_checked_in_contract_preserves_all_live_public_tables_without_secrets() -> None:
    root = Path(__file__).resolve().parents[4]
    contract_path = (
        root / "apps" / "core-api" / "src" / "inkforge_core" / "db" / "schema-contract.json"
    )

    contract = load_schema_contract(contract_path)
    table_names = {table["name"] for table in contract["tables"]}
    rag_chunk = next(table for table in contract["tables"] if table["name"] == "RagChunk")
    embedding = next(column for column in rag_chunk["columns"] if column["name"] == "embedding")

    assert table_names == {
        "Chapter",
        "ChapterBeatPlan",
        "ChapterProgress",
        "ChapterQualityCheck",
        "ChapterWritingGoal",
        "Character",
        "CharacterExperience",
        "CharacterRelation",
        "CharacterStateChange",
        "CreditLedger",
        "Faction",
        "Foreshadowing",
        "Glossary",
        "Item",
        "Location",
        "Novel",
        "Outline",
        "OutlineNode",
        "PlotProgress",
        "RagChunk",
        "RagDocument",
        "ReferenceMaterial",
        "ReviewArtifact",
        "ReviewArtifactEvaluation",
        "ReviewArtifactRevision",
        "SceneBeat",
        "StoryBackground",
        "StylePortraitTask",
        "StyleReference",
        "TokenUsage",
        "User",
        "WorkflowRun",
        "WorkflowStep",
        "WorldSetting",
        "WritingBible",
        "WritingConfig",
        "WritingMessage",
        "WritingSession",
        "WritingStyle",
        "WritingTask",
        "_FactionTerritories",
        "_prisma_migrations",
    }
    assert embedding["formatType"] == "vector"
    assert set(contract) == {
        "contractVersion",
        "schema",
        "tables",
        "enums",
        "extensions",
        "fingerprint",
        "source",
    }
    assert set(contract["source"]) == {
        "product",
        "serverVersion",
        "serverVersionNum",
        "sourceId",
    }
    assert re.fullmatch(r"[0-9a-f]{64}", contract["source"]["sourceId"])

    forbidden_keys = {"databaseurl", "host", "port", "user", "password", "databasename", "path"}

    def assert_safe(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(key.lower() for key in value)
            for child in value.values():
                assert_safe(child)
        elif isinstance(value, list):
            for child in value:
                assert_safe(child)
        elif isinstance(value, str):
            assert re.match(r"^[A-Za-z]:[\\/]", value) is None
            assert not value.startswith("/")

    assert_safe(contract)


class FakeMappings:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows

    def all(self) -> list[Mapping[str, object]]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._rows)


class RecordingConnection:
    def __init__(self, result_sets: list[list[Mapping[str, object]]]) -> None:
        self.result_sets = list(result_sets)
        self.statements: list[str] = []

    async def execute(
        self, statement: object, parameters: Mapping[str, object] | None = None
    ) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if sql.lstrip().upper().startswith("SET "):
            return FakeResult([])
        return FakeResult(self.result_sets.pop(0))


def catalog_result_sets(
    *,
    server_version: str = "17.5",
    server_version_num: int = 170005,
    database_name: str = "private_database",
    server_address: str = "192.0.2.10",
    server_port: int = 5432,
) -> list[list[Mapping[str, object]]]:
    return [
        [
            {
                "server_version": server_version,
                "server_version_num": server_version_num,
                "database_name": database_name,
                "server_address": server_address,
                "server_port": server_port,
            }
        ],
        [{"table_name": "RagChunk"}],
        [
            {
                "table_name": "RagChunk",
                "column_name": "embedding",
                "format_type": "vector(1536)",
                "udt_name": "vector",
                "nullable": False,
                "column_default": None,
            }
        ],
        [
            {
                "table_name": "RagChunk",
                "constraint_name": "RagChunk_pkey",
                "position": 1,
                "column_name": "embedding",
                "is_deferrable": False,
                "is_deferred": False,
                "is_validated": True,
            }
        ],
        [
            {
                "table_name": "RagChunk",
                "constraint_name": "RagChunk_documentId_fkey",
                "position": 1,
                "column_name": "documentId",
                "target_schema": "public",
                "target_table": "RagDocument",
                "target_column": "id",
                "on_update": "CASCADE",
                "on_delete": "CASCADE",
                "match_type": "SIMPLE",
                "is_deferrable": False,
                "is_deferred": False,
                "is_validated": True,
            }
        ],
        [
            {
                "table_name": "RagChunk",
                "constraint_name": "RagChunk_embedding_key",
                "position": 1,
                "column_name": "embedding",
                "is_deferrable": False,
                "is_deferred": False,
                "is_validated": True,
            }
        ],
        [
            {
                "table_name": "RagChunk",
                "index_name": "RagChunk_mixed_idx",
                "is_unique": False,
                "method": "hnsw",
                "position": 1,
                "is_key": True,
                "column_name": "embedding",
                "expression": None,
                "opclass_schema": "public",
                "opclass_name": "vector_cosine_ops",
                "collation_schema": None,
                "collation_name": None,
                "order_direction": "ASC",
                "nulls_position": "LAST",
                "predicate": None,
                "is_valid": True,
                "is_ready": True,
                "nulls_not_distinct": False,
                "rel_options": ["fillfactor=90"],
                "tablespace_name": "fastspace",
            },
            {
                "table_name": "RagChunk",
                "index_name": "RagChunk_mixed_idx",
                "is_unique": False,
                "method": "hnsw",
                "position": 2,
                "is_key": True,
                "column_name": None,
                "expression": "lower(text)",
                "opclass_schema": "pg_catalog",
                "opclass_name": "text_ops",
                "collation_schema": "pg_catalog",
                "collation_name": "default",
                "order_direction": "DESC",
                "nulls_position": "FIRST",
                "predicate": None,
                "is_valid": True,
                "is_ready": True,
                "nulls_not_distinct": False,
                "rel_options": ["fillfactor=90"],
                "tablespace_name": "fastspace",
            },
            {
                "table_name": "RagChunk",
                "index_name": "RagChunk_mixed_idx",
                "is_unique": False,
                "method": "hnsw",
                "position": 3,
                "is_key": False,
                "column_name": "novelId",
                "expression": None,
                "opclass_schema": None,
                "opclass_name": None,
                "collation_schema": None,
                "collation_name": None,
                "order_direction": None,
                "nulls_position": None,
                "predicate": None,
                "is_valid": True,
                "is_ready": True,
                "nulls_not_distinct": False,
                "rel_options": ["fillfactor=90"],
                "tablespace_name": "fastspace",
            },
        ],
        [{"enum_name": "ChapterStatus", "enum_value": "drafting", "sort_order": 1.0}],
        [
            {"extension_name": "plpgsql", "version": "1.0"},
            {"extension_name": "vector", "version": "0.8.1"},
        ],
    ]


def temporary_contract_files(directory: Path, output: Path) -> list[Path]:
    return list(directory.glob(f".{output.name}.*.tmp"))


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


async def test_inspection_uses_only_catalog_selects_and_preserves_vector_dimension() -> None:
    connection = RecordingConnection(catalog_result_sets())

    contract = await inspect_schema(connection)

    assert contract["tables"][0]["columns"][0]["formatType"] == "vector(1536)"
    assert contract["source"]["product"] == "PostgreSQL"
    assert contract["source"]["serverVersion"] == "17.5"
    assert contract["source"]["serverVersionNum"] == 170005
    assert re.fullmatch(r"[0-9a-f]{64}", contract["source"]["sourceId"])
    assert "private_database" not in json.dumps(contract)
    assert "192.0.2.10" not in json.dumps(contract)
    assert contract["extensions"] == [
        {"name": "plpgsql", "installed": True, "version": "1.0"},
        {"name": "vector", "installed": True, "version": "0.8.1"},
    ]
    mixed_index = next(
        index
        for index in contract["tables"][0]["indexes"]
        if index["name"] == "RagChunk_mixed_idx"
    )
    assert [item["kind"] for item in mixed_index["keyItems"]] == ["column", "expression"]
    assert [item["opclass"] for item in mixed_index["keyItems"]] == [
        "vector_cosine_ops",
        "text_ops",
    ]
    assert mixed_index["keyItems"][1]["order"] == "DESC"
    assert mixed_index["keyItems"][1]["nulls"] == "FIRST"
    assert mixed_index["includeColumns"] == ["novelId"]
    assert mixed_index["valid"] is True
    assert mixed_index["ready"] is True
    assert mixed_index["nullsNotDistinct"] is False
    assert mixed_index["options"] == ["fillfactor=90"]
    assert mixed_index["tablespace"] == "fastspace"
    assert contract["tables"][0]["primaryKey"] == {
        "name": "RagChunk_pkey",
        "columns": ["embedding"],
        "deferrable": False,
        "initiallyDeferred": False,
        "validated": True,
    }
    assert contract["tables"][0]["foreignKeys"][0]["matchType"] == "SIMPLE"
    assert contract["tables"][0]["uniqueConstraints"][0]["validated"] is True
    assert len(connection.statements) == 9
    for sql in connection.statements:
        normalized = sql.lstrip().upper()
        assert normalized.startswith("SELECT")
        assert not any(
            forbidden in normalized
            for forbidden in (
                "CREATE ",
                "ALTER ",
                "DROP ",
                "INSERT ",
                "UPDATE ",
                "DELETE ",
                "TRUNCATE ",
            )
        )


async def test_source_id_distinguishes_database_identity_without_affecting_fingerprint() -> None:
    first = await inspect_schema(RecordingConnection(catalog_result_sets()))
    second = await inspect_schema(
        RecordingConnection(
            catalog_result_sets(
                database_name="another_private_database",
                server_address="198.51.100.20",
            )
        )
    )

    assert first["source"]["sourceId"] != second["source"]["sourceId"]
    assert canonical_fingerprint(first) == canonical_fingerprint(second)
    assert compare_schema_contract(first, second) == []


async def test_pg14_index_query_does_not_reference_new_catalog_column() -> None:
    connection = RecordingConnection(
        catalog_result_sets(server_version="14.12", server_version_num=140012)
    )

    contract = await inspect_schema(connection)

    index_sql = next(sql for sql in connection.statements if "pg_catalog.pg_index" in sql)
    assert "index_info.indnullsnotdistinct" not in index_sql
    assert "to_jsonb(index_info)" in index_sql
    assert contract["tables"][0]["indexes"][0]["nullsNotDistinct"] is False


class FakeTransactionContext:
    def __init__(self, connection: RecordingConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> RecordingConnection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: RecordingConnection) -> None:
        self.connection = connection
        self.disposed = False

    def begin(self) -> FakeTransactionContext:
        return FakeTransactionContext(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


async def test_shared_engine_schema_verification_never_disposes_main_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = tmp_path / "schema-contract.json"
    expected = sample_contract()
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(expected)), encoding="utf-8"
    )
    engine = FakeEngine(RecordingConnection(catalog_result_sets()))

    async def exact_inspection(*args: object, **kwargs: object) -> dict[str, Any]:
        return copy.deepcopy(expected)

    monkeypatch.setattr(schema_guard, "inspect_schema", exact_inspection)

    result = await verify_live_schema_with_engine(engine, contract_path)  # type: ignore[arg-type]

    assert result.ready is True
    assert engine.disposed is False
    assert engine.connection.statements[:2] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL search_path = pg_catalog, public",
    ]


async def test_temporary_guard_engine_uses_shared_url_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = tmp_path / "schema-contract.json"
    expected = sample_contract()
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(expected)), encoding="utf-8"
    )
    engine = FakeEngine(RecordingConnection(catalog_result_sets()))
    captured: dict[str, Any] = {}

    def create_engine(url: object, **kwargs: object) -> FakeEngine:
        captured["url"] = url
        captured.update(kwargs)
        return engine

    async def exact_inspection(*args: object, **kwargs: object) -> dict[str, Any]:
        return copy.deepcopy(expected)

    monkeypatch.setattr(schema_guard, "create_async_engine", create_engine)
    monkeypatch.setattr(schema_guard, "inspect_schema", exact_inspection)

    result = await verify_live_schema(
        "postgresql://user:credential@database/inkforge?sslmode=allow&application_name=schema-guard",
        contract_path,
    )

    assert result.ready is True
    assert captured["url"].drivername == "postgresql+asyncpg"
    assert captured["url"].query == {}
    assert captured["connect_args"] == {
        "ssl": "allow",
        "server_settings": {"application_name": "schema-guard"},
    }


async def test_export_refuses_existing_file_by_default_and_overwrites_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "schema-contract.json"
    output.write_text("旧内容", encoding="utf-8")
    connection = RecordingConnection(catalog_result_sets())
    engine = FakeEngine(connection)
    monkeypatch.setattr(schema_guard, "create_async_engine", lambda *args, **kwargs: engine)

    with pytest.raises(FileExistsError, match="已存在"):
        await export_schema_contract("postgresql+asyncpg://secret", output)
    assert connection.statements == []

    exported = await export_schema_contract(
        "postgresql+asyncpg://secret", output, overwrite=True
    )

    assert connection.statements[0].lstrip().upper().startswith("SET TRANSACTION READ ONLY")
    assert connection.statements[1].strip() == "SET LOCAL search_path = pg_catalog, public"
    assert load_schema_contract(output) == exported
    assert temporary_contract_files(tmp_path, output) == []
    assert engine.disposed is True


class FailingTransactionContext:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self) -> None:
        raise self.error

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingEngine:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def begin(self) -> FailingTransactionContext:
        return FailingTransactionContext(self.error)

    async def dispose(self) -> None:
        return None


async def test_connection_error_is_sanitized_and_not_reported_as_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_url = (
        "postgresql+asyncpg://secret-user:secret-password@secret-host/private-db"  # noqa: S105
    )
    contract_path = tmp_path / "schema-contract.json"
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(sample_contract())), encoding="utf-8"
    )
    engine = FailingEngine(RuntimeError(f"无法连接 {secret_url}"))
    monkeypatch.setattr(schema_guard, "create_async_engine", lambda *args, **kwargs: engine)

    with pytest.raises(SchemaConnectionError) as caught:
        await verify_live_schema(secret_url, contract_path)

    rendered = str(caught.value)
    assert "数据库结构不一致" not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert caught.value.diagnostic == "connection_failed"
    assert caught.value.exception_type == "RuntimeError"
    for secret in (secret_url, "secret-user", "secret-password", "secret-host", "private-db"):
        assert secret not in rendered


async def test_engine_creation_error_is_inside_sanitized_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_url = "postgresql+asyncpg://private:credential@hidden/server"  # noqa: S105
    contract_path = tmp_path / "schema-contract.json"
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(sample_contract())), encoding="utf-8"
    )

    def fail_engine_creation(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"引擎创建失败：{secret_url}")

    monkeypatch.setattr(schema_guard, "create_async_engine", fail_engine_creation)

    with pytest.raises(SchemaConnectionError) as caught:
        await verify_live_schema(secret_url, contract_path)

    assert caught.value.diagnostic == "engine_creation_failed"
    assert caught.value.exception_type == "RuntimeError"
    assert secret_url not in str(caught.value)
    assert caught.value.__cause__ is None


async def test_inspection_and_dispose_errors_are_sanitized_but_internal_errors_are_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "SECRET-INTERNAL-DIAGNOSTIC"  # noqa: S105
    contract_path = tmp_path / "schema-contract.json"
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(sample_contract())), encoding="utf-8"
    )
    engine = FakeEngine(RecordingConnection(catalog_result_sets()))
    monkeypatch.setattr(schema_guard, "create_async_engine", lambda *args, **kwargs: engine)

    async def fail_inspection(*args: object, **kwargs: object) -> dict[str, Any]:
        raise KeyError(secret)

    monkeypatch.setattr(schema_guard, "inspect_schema", fail_inspection)
    with pytest.raises(SchemaConnectionError) as inspection_error:
        await verify_live_schema("postgresql+asyncpg://unused", contract_path)

    assert inspection_error.value.diagnostic == "inspection_failed"
    assert inspection_error.value.exception_type == "KeyError"
    assert secret not in str(inspection_error.value)

    class DisposeFailingEngine(FakeEngine):
        async def dispose(self) -> None:
            raise RuntimeError(secret)

    async def successful_inspection(*args: object, **kwargs: object) -> dict[str, Any]:
        return copy.deepcopy(sample_contract())

    monkeypatch.setattr(schema_guard, "inspect_schema", successful_inspection)
    monkeypatch.setattr(
        schema_guard,
        "create_async_engine",
        lambda *args, **kwargs: DisposeFailingEngine(
            RecordingConnection(catalog_result_sets())
        ),
    )
    with pytest.raises(SchemaConnectionError) as dispose_error:
        await verify_live_schema("postgresql+asyncpg://unused", contract_path)

    assert dispose_error.value.diagnostic == "dispose_failed"
    assert dispose_error.value.exception_type == "RuntimeError"
    assert secret not in str(dispose_error.value)

    monkeypatch.undo()
    with pytest.raises(KeyError):
        await inspect_schema(RecordingConnection([[{}]]))


async def test_missing_inspection_result_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = tmp_path / "schema-contract.json"
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(sample_contract())), encoding="utf-8"
    )
    monkeypatch.setattr(
        schema_guard,
        "create_async_engine",
        lambda *args, **kwargs: FakeEngine(RecordingConnection(catalog_result_sets())),
    )

    async def missing_inspection(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(schema_guard, "inspect_schema", missing_inspection)

    with pytest.raises(SchemaConnectionError) as caught:
        await verify_live_schema("postgresql+asyncpg://unused", contract_path)

    assert caught.value.diagnostic == "inspection_failed"
    assert caught.value.exception_type == "MissingInspectionResult"


async def test_verify_live_schema_returns_exact_ready_and_single_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = tmp_path / "schema-contract.json"
    expected = sample_contract()
    contract_path.write_text(
        json.dumps(add_contract_fingerprint(expected)), encoding="utf-8"
    )

    async def inspect_exact(database_url: str, schema: str) -> dict[str, Any]:
        actual = copy.deepcopy(expected)
        actual["source"] = {
            "product": "PostgreSQL",
            "serverVersion": "14.24",
            "serverVersionNum": 140024,
            "sourceId": "b" * 64,
        }
        return actual

    monkeypatch.setattr(schema_guard, "_inspect_live", inspect_exact)
    ready_result = await verify_live_schema("postgresql+asyncpg://unused", contract_path)

    assert ready_result.ready is True
    assert ready_result.diffs == []
    assert ready_result.fingerprint == canonical_fingerprint(expected)

    async def inspect_drift(database_url: str, schema: str) -> dict[str, Any]:
        actual = copy.deepcopy(expected)
        actual["tables"][1]["columns"][0]["formatType"] = "vector(1536)"
        return actual

    monkeypatch.setattr(schema_guard, "_inspect_live", inspect_drift)
    drift_result = await verify_live_schema("postgresql+asyncpg://unused", contract_path)

    assert drift_result.ready is False
    assert [diff.path for diff in drift_result.diffs] == [
        "tables.RagChunk.columns.embedding.formatType"
    ]


async def test_default_export_does_not_overwrite_file_created_during_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "schema-contract.json"

    async def inspect_with_race(database_url: str, schema: str) -> dict[str, Any]:
        output.write_text("竞争写入内容", encoding="utf-8")
        return sample_contract()

    monkeypatch.setattr(schema_guard, "_inspect_live", inspect_with_race)

    with pytest.raises(FileExistsError):
        await export_schema_contract("postgresql+asyncpg://unused", output)

    assert output.read_text(encoding="utf-8") == "竞争写入内容"


async def test_cli_success_prints_safe_source_identifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository_root()
    namespace = runpy.run_path(str(root / "scripts" / "export_schema_contract.py"))
    run = namespace["_run"]
    secret_url = "postgresql+asyncpg://private:credential@hidden/server"  # noqa: S105

    async def fake_export(*args: object, **kwargs: object) -> dict[str, Any]:
        return add_contract_fingerprint(sample_contract())

    run.__globals__["export_schema_contract"] = fake_export
    result = await run(
        argparse.Namespace(
            database_url=secret_url,
            output=tmp_path / "schema-contract.json",
            overwrite=False,
        )
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "来源 aaaaaaaaaaaa" in output
    assert secret_url not in output


def test_cli_help_and_required_arguments() -> None:
    root = Path(__file__).resolve().parents[4]
    script = root / "scripts" / "export_schema_contract.py"

    help_result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    missing_result = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0
    assert "--database-url" in help_result.stdout
    assert "--output" in help_result.stdout
    assert "--overwrite" in help_result.stdout
    assert missing_result.returncode != 0
    assert "--database-url" in missing_result.stderr
    assert "--output" in missing_result.stderr
