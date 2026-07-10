"""以只读方式采集、导出并验证 PostgreSQL 数据库结构。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

Contract = dict[str, Any]


class ContractIntegrityError(ValueError):
    """结构契约本身损坏或指纹不自洽。"""


class SchemaConnectionError(RuntimeError):
    """无法安全读取实时数据库结构。"""


@dataclass(frozen=True, slots=True)
class SchemaDiff:
    """一项字段级数据库结构差异。"""

    path: str
    expected: object
    actual: object
    message: str


@dataclass(frozen=True, slots=True)
class SchemaVerificationResult:
    """实时数据库结构验证结果。"""

    ready: bool
    fingerprint: str
    diffs: list[SchemaDiff]


class _MappingResult(Protocol):
    def all(self) -> Sequence[Mapping[str, object]]: ...


class _ExecutionResult(Protocol):
    def mappings(self) -> _MappingResult: ...


class CatalogConnection(Protocol):
    async def execute(
        self, statement: object, parameters: Mapping[str, object] | None = None
    ) -> _ExecutionResult: ...


_TABLES_QUERY = """
SELECT table_class.relname AS table_name
FROM pg_catalog.pg_class AS table_class
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = :schema
  AND table_class.relkind = 'r'
ORDER BY table_class.relname
"""

_COLUMNS_QUERY = """
SELECT
  table_class.relname AS table_name,
  attribute.attname AS column_name,
  pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS format_type,
  type_info.typname AS udt_name,
  NOT attribute.attnotnull AS nullable,
  pg_catalog.pg_get_expr(default_info.adbin, default_info.adrelid) AS column_default
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS table_class
  ON table_class.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
JOIN pg_catalog.pg_type AS type_info
  ON type_info.oid = attribute.atttypid
LEFT JOIN pg_catalog.pg_attrdef AS default_info
  ON default_info.adrelid = attribute.attrelid
 AND default_info.adnum = attribute.attnum
WHERE namespace.nspname = :schema
  AND table_class.relkind = 'r'
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped
ORDER BY table_class.relname, attribute.attnum
"""

_PRIMARY_KEYS_QUERY = """
SELECT
  table_class.relname AS table_name,
  constraint_info.conname AS constraint_name,
  key_position.ordinality AS position,
  attribute.attname AS column_name
FROM pg_catalog.pg_constraint AS constraint_info
JOIN pg_catalog.pg_class AS table_class
  ON table_class.oid = constraint_info.conrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
JOIN LATERAL unnest(constraint_info.conkey) WITH ORDINALITY AS key_position(attnum, ordinality)
  ON true
JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = table_class.oid
 AND attribute.attnum = key_position.attnum
WHERE namespace.nspname = :schema
  AND constraint_info.contype = 'p'
ORDER BY table_class.relname, constraint_info.conname, key_position.ordinality
"""

_FOREIGN_KEYS_QUERY = """
SELECT
  source_table.relname AS table_name,
  constraint_info.conname AS constraint_name,
  key_position.ordinality AS position,
  source_attribute.attname AS column_name,
  target_namespace.nspname AS target_schema,
  target_table.relname AS target_table,
  target_attribute.attname AS target_column,
  CASE constraint_info.confupdtype
    WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
    WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
  END AS on_update,
  CASE constraint_info.confdeltype
    WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
    WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
  END AS on_delete
FROM pg_catalog.pg_constraint AS constraint_info
JOIN pg_catalog.pg_class AS source_table
  ON source_table.oid = constraint_info.conrelid
JOIN pg_catalog.pg_namespace AS source_namespace
  ON source_namespace.oid = source_table.relnamespace
JOIN pg_catalog.pg_class AS target_table
  ON target_table.oid = constraint_info.confrelid
JOIN pg_catalog.pg_namespace AS target_namespace
  ON target_namespace.oid = target_table.relnamespace
JOIN LATERAL unnest(constraint_info.conkey, constraint_info.confkey)
  WITH ORDINALITY AS key_position(source_attnum, target_attnum, ordinality)
  ON true
JOIN pg_catalog.pg_attribute AS source_attribute
  ON source_attribute.attrelid = source_table.oid
 AND source_attribute.attnum = key_position.source_attnum
JOIN pg_catalog.pg_attribute AS target_attribute
  ON target_attribute.attrelid = target_table.oid
 AND target_attribute.attnum = key_position.target_attnum
WHERE source_namespace.nspname = :schema
  AND constraint_info.contype = 'f'
ORDER BY source_table.relname, constraint_info.conname, key_position.ordinality
"""

_UNIQUE_CONSTRAINTS_QUERY = """
SELECT
  table_class.relname AS table_name,
  constraint_info.conname AS constraint_name,
  key_position.ordinality AS position,
  attribute.attname AS column_name
FROM pg_catalog.pg_constraint AS constraint_info
JOIN pg_catalog.pg_class AS table_class
  ON table_class.oid = constraint_info.conrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
JOIN LATERAL unnest(constraint_info.conkey) WITH ORDINALITY AS key_position(attnum, ordinality)
  ON true
JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = table_class.oid
 AND attribute.attnum = key_position.attnum
WHERE namespace.nspname = :schema
  AND constraint_info.contype = 'u'
ORDER BY table_class.relname, constraint_info.conname, key_position.ordinality
"""

_INDEXES_QUERY = """
SELECT
  table_class.relname AS table_name,
  index_class.relname AS index_name,
  index_info.indisunique AS is_unique,
  access_method.amname AS method,
  key_position.position,
  indexed_attribute.attname AS column_name,
  CASE WHEN indexed_attribute.attname IS NULL
    THEN pg_catalog.pg_get_indexdef(index_info.indexrelid, key_position.position, true)
    ELSE NULL
  END AS expression,
  pg_catalog.pg_get_expr(index_info.indpred, index_info.indrelid) AS predicate
FROM pg_catalog.pg_index AS index_info
JOIN pg_catalog.pg_class AS table_class
  ON table_class.oid = index_info.indrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
JOIN pg_catalog.pg_class AS index_class
  ON index_class.oid = index_info.indexrelid
JOIN pg_catalog.pg_am AS access_method
  ON access_method.oid = index_class.relam
JOIN LATERAL generate_series(1, index_info.indnkeyatts) AS key_position(position)
  ON true
LEFT JOIN pg_catalog.pg_attribute AS indexed_attribute
  ON indexed_attribute.attrelid = table_class.oid
 AND indexed_attribute.attnum = (index_info.indkey::smallint[])[key_position.position - 1]
WHERE namespace.nspname = :schema
  AND table_class.relkind = 'r'
ORDER BY table_class.relname, index_class.relname, key_position.position
"""

_ENUMS_QUERY = """
SELECT
  type_info.typname AS enum_name,
  enum_info.enumlabel AS enum_value,
  enum_info.enumsortorder AS sort_order
FROM pg_catalog.pg_type AS type_info
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = type_info.typnamespace
JOIN pg_catalog.pg_enum AS enum_info
  ON enum_info.enumtypid = type_info.oid
WHERE namespace.nspname = :schema
ORDER BY type_info.typname, enum_info.enumsortorder
"""

_EXTENSIONS_QUERY = """
SELECT extension_info.extname AS extension_name, extension_info.extversion AS version
FROM pg_catalog.pg_extension AS extension_info
WHERE extension_info.extname = 'vector'
ORDER BY extension_info.extname
"""


def canonical_fingerprint(contract: Mapping[str, object]) -> str:
    """计算忽略顶层指纹字段的稳定 SHA-256。"""

    payload = {key: value for key, value in contract.items() if key != "fingerprint"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def add_contract_fingerprint(contract: Mapping[str, object]) -> Contract:
    """返回带自洽指纹的结构契约副本。"""

    result = cast(Contract, json.loads(json.dumps(contract, ensure_ascii=False)))
    result.pop("fingerprint", None)
    result["fingerprint"] = canonical_fingerprint(result)
    return result


def load_schema_contract(path: str | Path) -> Contract:
    """加载结构契约，并在使用前验证其指纹。"""

    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractIntegrityError("数据库结构契约无法读取或不是有效 JSON。") from exc
    if not isinstance(loaded, dict):
        raise ContractIntegrityError("数据库结构契约顶层必须是对象。")
    contract = cast(Contract, loaded)
    fingerprint = contract.get("fingerprint")
    if not isinstance(fingerprint, str) or fingerprint != canonical_fingerprint(contract):
        raise ContractIntegrityError("数据库结构契约指纹不自洽，文件可能已损坏。")
    return contract


def _normalize_default(value: object) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


async def _rows(
    connection: CatalogConnection, query: str, parameters: Mapping[str, object]
) -> list[Mapping[str, object]]:
    result = await connection.execute(text(query), parameters)
    return list(result.mappings().all())


def _group_constraint_columns(
    rows: Sequence[Mapping[str, object]], tables: Mapping[str, Contract]
) -> None:
    grouped: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        key = (str(row["table_name"]), str(row["constraint_name"]))
        grouped.setdefault(key, []).append(str(row["column_name"]))
    for (table_name, constraint_name), columns in grouped.items():
        tables[table_name]["uniqueConstraints"].append(
            {"name": constraint_name, "columns": columns}
        )


async def inspect_schema(
    connection: CatalogConnection, schema: str = "public"
) -> Contract:
    """仅通过 PostgreSQL catalog 查询采集指定 schema 的结构。"""

    parameters: Mapping[str, object] = {"schema": schema}
    table_rows = await _rows(connection, _TABLES_QUERY, parameters)
    column_rows = await _rows(connection, _COLUMNS_QUERY, parameters)
    primary_key_rows = await _rows(connection, _PRIMARY_KEYS_QUERY, parameters)
    foreign_key_rows = await _rows(connection, _FOREIGN_KEYS_QUERY, parameters)
    unique_rows = await _rows(connection, _UNIQUE_CONSTRAINTS_QUERY, parameters)
    index_rows = await _rows(connection, _INDEXES_QUERY, parameters)
    enum_rows = await _rows(connection, _ENUMS_QUERY, parameters)
    extension_rows = await _rows(connection, _EXTENSIONS_QUERY, parameters)

    tables: dict[str, Contract] = {}
    for row in table_rows:
        name = str(row["table_name"])
        tables[name] = {
            "name": name,
            "columns": [],
            "primaryKey": None,
            "foreignKeys": [],
            "uniqueConstraints": [],
            "indexes": [],
        }

    for row in column_rows:
        tables[str(row["table_name"])]["columns"].append(
            {
                "name": str(row["column_name"]),
                "formatType": str(row["format_type"]),
                "udtName": str(row["udt_name"]),
                "nullable": bool(row["nullable"]),
                "default": _normalize_default(row["column_default"]),
            }
        )

    primary_keys: dict[tuple[str, str], list[str]] = {}
    for row in primary_key_rows:
        key = (str(row["table_name"]), str(row["constraint_name"]))
        primary_keys.setdefault(key, []).append(str(row["column_name"]))
    for (table_name, constraint_name), columns in primary_keys.items():
        tables[table_name]["primaryKey"] = {"name": constraint_name, "columns": columns}

    foreign_keys: dict[tuple[str, str], Contract] = {}
    for row in foreign_key_rows:
        table_name = str(row["table_name"])
        constraint_name = str(row["constraint_name"])
        key = (table_name, constraint_name)
        foreign_key = foreign_keys.setdefault(
            key,
            {
                "name": constraint_name,
                "columns": [],
                "targetSchema": str(row["target_schema"]),
                "targetTable": str(row["target_table"]),
                "targetColumns": [],
                "onUpdate": str(row["on_update"]),
                "onDelete": str(row["on_delete"]),
            },
        )
        foreign_key["columns"].append(str(row["column_name"]))
        foreign_key["targetColumns"].append(str(row["target_column"]))
    for (table_name, _), foreign_key in foreign_keys.items():
        tables[table_name]["foreignKeys"].append(foreign_key)

    _group_constraint_columns(unique_rows, tables)

    indexes: dict[tuple[str, str], Contract] = {}
    for row in index_rows:
        table_name = str(row["table_name"])
        index_name = str(row["index_name"])
        index = indexes.setdefault(
            (table_name, index_name),
            {
                "name": index_name,
                "unique": bool(row["is_unique"]),
                "method": str(row["method"]),
                "columns": [],
                "expressions": [],
                "predicate": _normalize_default(row["predicate"]),
            },
        )
        if row["column_name"] is None:
            index["expressions"].append(str(row["expression"]))
        else:
            index["columns"].append(str(row["column_name"]))
    for (table_name, _), index in indexes.items():
        tables[table_name]["indexes"].append(index)

    enums: dict[str, list[str]] = {}
    for row in enum_rows:
        enums.setdefault(str(row["enum_name"]), []).append(str(row["enum_value"]))

    vector_extension: Contract = {"name": "vector", "installed": False, "version": None}
    for row in extension_rows:
        if str(row["extension_name"]) == "vector":
            vector_extension = {
                "name": "vector",
                "installed": True,
                "version": str(row["version"]),
            }

    for table in tables.values():
        table["columns"].sort(key=lambda item: item["name"])
        table["foreignKeys"].sort(key=lambda item: item["name"])
        table["uniqueConstraints"].sort(key=lambda item: item["name"])
        table["indexes"].sort(key=lambda item: item["name"])

    return {
        "contractVersion": 1,
        "schema": schema,
        "tables": [tables[name] for name in sorted(tables)],
        "enums": [{"name": name, "values": enums[name]} for name in sorted(enums)],
        "extensions": [vector_extension],
    }


def _named_items(value: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, list):
        return {}
    return {
        str(item["name"]): item
        for item in value
        if isinstance(item, dict) and "name" in item
    }


def _append_value_diff(
    diffs: list[SchemaDiff], path: str, expected: object, actual: object
) -> None:
    if expected == actual:
        return
    if path.endswith("formatType") and (
        "vector" in str(expected).lower() or "vector" in str(actual).lower()
    ):
        message = f"向量或列类型不一致：期望 {expected!r}，实际 {actual!r}。"
    else:
        message = f"结构字段不一致：期望 {expected!r}，实际 {actual!r}。"
    diffs.append(SchemaDiff(path, expected, actual, message))


def _compare_mapping(
    diffs: list[SchemaDiff],
    path: str,
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    ignored: frozenset[str] = frozenset(),
) -> None:
    for key in sorted((set(expected) | set(actual)) - ignored):
        _append_value_diff(diffs, f"{path}.{key}", expected.get(key), actual.get(key))


def _compare_named_collection(
    diffs: list[SchemaDiff],
    path: str,
    expected_value: object,
    actual_value: object,
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    expected = _named_items(expected_value)
    actual = _named_items(actual_value)
    for name in sorted(set(expected) - set(actual)):
        diffs.append(
            SchemaDiff(f"{path}.{name}", expected[name], None, f"缺少结构项：{path}.{name}。")
        )
    for name in sorted(set(actual) - set(expected)):
        diffs.append(
            SchemaDiff(f"{path}.{name}", None, actual[name], f"存在额外结构项：{path}.{name}。")
        )
    return expected, actual


def _extension_version_key(value: object) -> object:
    if not isinstance(value, str):
        return value
    parts = value.split(".")
    return tuple(parts[:2])


def compare_schema_contract(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> list[SchemaDiff]:
    """返回稳定排序的字段级结构差异，补丁扩展版本不视为漂移。"""

    diffs: list[SchemaDiff] = []
    _append_value_diff(
        diffs, "contractVersion", expected.get("contractVersion"), actual.get("contractVersion")
    )
    _append_value_diff(diffs, "schema", expected.get("schema"), actual.get("schema"))

    expected_tables, actual_tables = _compare_named_collection(
        diffs, "tables", expected.get("tables"), actual.get("tables")
    )
    for table_name in sorted(set(expected_tables) & set(actual_tables)):
        expected_table = expected_tables[table_name]
        actual_table = actual_tables[table_name]
        table_path = f"tables.{table_name}"
        expected_columns, actual_columns = _compare_named_collection(
            diffs,
            f"{table_path}.columns",
            expected_table.get("columns"),
            actual_table.get("columns"),
        )
        for column_name in sorted(set(expected_columns) & set(actual_columns)):
            _compare_mapping(
                diffs,
                f"{table_path}.columns.{column_name}",
                expected_columns[column_name],
                actual_columns[column_name],
                ignored=frozenset({"name"}),
            )

        expected_primary = expected_table.get("primaryKey")
        actual_primary = actual_table.get("primaryKey")
        if isinstance(expected_primary, dict) and isinstance(actual_primary, dict):
            _compare_mapping(
                diffs,
                f"{table_path}.primaryKey",
                expected_primary,
                actual_primary,
            )
        else:
            _append_value_diff(
                diffs, f"{table_path}.primaryKey", expected_primary, actual_primary
            )

        for collection_name in ("foreignKeys", "uniqueConstraints", "indexes"):
            expected_items, actual_items = _compare_named_collection(
                diffs,
                f"{table_path}.{collection_name}",
                expected_table.get(collection_name),
                actual_table.get(collection_name),
            )
            for item_name in sorted(set(expected_items) & set(actual_items)):
                _compare_mapping(
                    diffs,
                    f"{table_path}.{collection_name}.{item_name}",
                    expected_items[item_name],
                    actual_items[item_name],
                    ignored=frozenset({"name"}),
                )

    expected_enums, actual_enums = _compare_named_collection(
        diffs, "enums", expected.get("enums"), actual.get("enums")
    )
    for enum_name in sorted(set(expected_enums) & set(actual_enums)):
        _append_value_diff(
            diffs,
            f"enums.{enum_name}.values",
            expected_enums[enum_name].get("values"),
            actual_enums[enum_name].get("values"),
        )

    expected_extensions, actual_extensions = _compare_named_collection(
        diffs, "extensions", expected.get("extensions"), actual.get("extensions")
    )
    for extension_name in sorted(set(expected_extensions) & set(actual_extensions)):
        expected_extension = expected_extensions[extension_name]
        actual_extension = actual_extensions[extension_name]
        extension_path = f"extensions.{extension_name}"
        expected_installed = expected_extension.get("installed")
        actual_installed = actual_extension.get("installed")
        _append_value_diff(
            diffs, f"{extension_path}.installed", expected_installed, actual_installed
        )
        if expected_installed is True and actual_installed is True:
            _append_value_diff(
                diffs,
                f"{extension_path}.version",
                _extension_version_key(expected_extension.get("version")),
                _extension_version_key(actual_extension.get("version")),
            )

    return sorted(diffs, key=lambda diff: (diff.path, repr(diff.expected), repr(diff.actual)))


def _async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


async def _inspect_live(database_url: str, schema: str) -> Contract:
    engine: AsyncEngine = create_async_engine(
        _async_database_url(database_url), pool_pre_ping=True
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            return await inspect_schema(cast(CatalogConnection, connection), schema)
    except Exception:
        raise SchemaConnectionError(
            "无法以只读方式连接并检查 PostgreSQL 数据库结构。"
        ) from None
    finally:
        await engine.dispose()


def _write_contract_atomic(contract: Mapping[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(contract, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _path_exists(path: Path) -> bool:
    return path.exists()


async def export_schema_contract(
    database_url: str,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    schema: str = "public",
) -> Contract:
    """在显式只读事务中采集结构，并原子写入带指纹契约。"""

    destination = Path(output_path)
    if _path_exists(destination) and not overwrite:
        raise FileExistsError("数据库结构契约已存在；必须显式允许覆盖。")
    contract = add_contract_fingerprint(await _inspect_live(database_url, schema))
    _write_contract_atomic(contract, destination)
    return contract


async def verify_live_schema(
    database_url: str, contract_path: str | Path
) -> SchemaVerificationResult:
    """验证实时结构与已签指纹契约是否逐字段一致。"""

    expected = load_schema_contract(contract_path)
    actual = add_contract_fingerprint(
        await _inspect_live(database_url, str(expected.get("schema", "public")))
    )
    diffs = compare_schema_contract(expected, actual)
    return SchemaVerificationResult(
        ready=not diffs,
        fingerprint=str(actual["fingerprint"]),
        diffs=diffs,
    )
