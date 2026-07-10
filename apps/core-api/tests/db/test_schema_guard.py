from __future__ import annotations

import copy
import json
import re
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
                "primaryKey": {"name": "Novel_pkey", "columns": ["id"]},
                "foreignKeys": [
                    {
                        "name": "Novel_userId_fkey",
                        "columns": ["userId"],
                        "targetSchema": "public",
                        "targetTable": "User",
                        "targetColumns": ["id"],
                        "onUpdate": "CASCADE",
                        "onDelete": "SET NULL",
                    }
                ],
                "uniqueConstraints": [],
                "indexes": [
                    {
                        "name": "Novel_userId_idx",
                        "unique": False,
                        "method": "btree",
                        "columns": ["userId"],
                        "expressions": [],
                        "predicate": None,
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
        "extensions": [{"name": "vector", "installed": True, "version": "0.8.1"}],
    }


def test_canonical_fingerprint_is_stable_and_excludes_fingerprint() -> None:
    contract = sample_contract()
    reordered = {
        "tables": contract["tables"],
        "schema": contract["schema"],
        "extensions": contract["extensions"],
        "contractVersion": contract["contractVersion"],
        "enums": contract["enums"],
        "fingerprint": "应被忽略",
    }

    first = canonical_fingerprint(contract)
    second = canonical_fingerprint(reordered)

    assert first == second
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
            "columns": [],
            "expressions": ["embedding vector_cosine_ops"],
            "predicate": None,
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


def test_compare_ignores_extension_patch_version_but_not_presence() -> None:
    expected = sample_contract()
    actual = copy.deepcopy(expected)
    actual["extensions"][0]["version"] = "0.8.9"

    assert compare_schema_contract(expected, actual) == []

    actual["extensions"][0]["installed"] = False
    diffs = compare_schema_contract(expected, actual)
    assert [diff.path for diff in diffs] == ["extensions.vector.installed"]


def test_checked_in_contract_preserves_all_live_public_tables_without_secrets() -> None:
    root = Path(__file__).resolve().parents[4]
    contract_path = (
        root / "apps" / "core-api" / "src" / "inkforge_core" / "db" / "schema-contract.json"
    )

    contract = load_schema_contract(contract_path)
    table_names = {table["name"] for table in contract["tables"]}
    rag_chunk = next(table for table in contract["tables"] if table["name"] == "RagChunk")
    embedding = next(column for column in rag_chunk["columns"] if column["name"] == "embedding")

    assert len(table_names) == 42
    assert {"_FactionTerritories", "_prisma_migrations"} <= table_names
    assert embedding["formatType"] == "vector"
    assert set(contract) == {
        "contractVersion",
        "schema",
        "tables",
        "enums",
        "extensions",
        "fingerprint",
    }

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
        if sql.lstrip().upper().startswith("SET TRANSACTION READ ONLY"):
            return FakeResult([])
        return FakeResult(self.result_sets.pop(0))


def catalog_result_sets() -> list[list[Mapping[str, object]]]:
    return [
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
        [],
        [],
        [],
        [
            {
                "table_name": "RagChunk",
                "index_name": "RagChunk_embedding_idx",
                "is_unique": False,
                "method": "hnsw",
                "column_name": None,
                "expression": "embedding vector_cosine_ops",
                "predicate": None,
            },
            {
                "table_name": "RagChunk",
                "index_name": "RagChunk_novelId_idx",
                "is_unique": False,
                "method": "btree",
                "column_name": "novelId",
                "expression": None,
                "predicate": None,
            },
        ],
        [{"enum_name": "ChapterStatus", "enum_value": "drafting", "sort_order": 1.0}],
        [{"extension_name": "vector", "version": "0.8.1"}],
    ]


def temporary_contract_files(directory: Path, output: Path) -> list[Path]:
    return list(directory.glob(f".{output.name}.*.tmp"))


async def test_inspection_uses_only_catalog_selects_and_preserves_vector_dimension() -> None:
    connection = RecordingConnection(catalog_result_sets())

    contract = await inspect_schema(connection)

    assert contract["tables"][0]["columns"][0]["formatType"] == "vector(1536)"
    assert contract["extensions"] == [
        {"name": "vector", "installed": True, "version": "0.8.1"}
    ]
    novel_index = next(
        index
        for index in contract["tables"][0]["indexes"]
        if index["name"] == "RagChunk_novelId_idx"
    )
    assert novel_index["columns"] == ["novelId"]
    assert len(connection.statements) == 8
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
    for secret in (secret_url, "secret-user", "secret-password", "secret-host", "private-db"):
        assert secret not in rendered


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
