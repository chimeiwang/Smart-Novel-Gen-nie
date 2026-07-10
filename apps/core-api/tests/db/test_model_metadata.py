from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine

CONTRACT_PATH = Path(__file__).parents[2] / "src" / "inkforge_core" / "db" / "schema-contract.json"
EXPECTED_MODEL_TABLES = {
    "User",
    "Novel",
    "Chapter",
    "ChapterQualityCheck",
    "ChapterProgress",
    "Character",
    "CharacterRelation",
    "CharacterExperience",
    "Item",
    "Location",
    "Faction",
    "Glossary",
    "StoryBackground",
    "WorldSetting",
    "WritingBible",
    "Outline",
    "PlotProgress",
    "ReferenceMaterial",
    "RagDocument",
    "RagChunk",
    "WritingStyle",
    "StyleReference",
    "StylePortraitTask",
    "Foreshadowing",
    "OutlineNode",
    "CharacterStateChange",
    "WritingConfig",
    "WritingTask",
    "WritingSession",
    "WritingMessage",
    "TokenUsage",
    "CreditLedger",
    "WorkflowRun",
    "WorkflowStep",
    "ReviewArtifact",
    "ReviewArtifactRevision",
    "ReviewArtifactEvaluation",
    "ChapterWritingGoal",
    "ChapterBeatPlan",
    "SceneBeat",
}
EXPECTED_TABLES = EXPECTED_MODEL_TABLES | {"_FactionTerritories"}


def _contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text("utf-8")))


def _business_contract_tables() -> dict[str, dict[str, Any]]:
    return {
        table["name"]: table
        for table in _contract()["tables"]
        if table["name"] != "_prisma_migrations"
    }


def _server_default_sql(column: Any) -> str | None:
    if column.server_default is None:
        return None
    return str(column.server_default.arg)


def _expected_python_type(udt_name: str) -> type[Any]:
    if udt_name == "text":
        return Text
    if udt_name == "int4":
        return Integer
    if udt_name == "int8":
        return BigInteger
    if udt_name == "bool":
        return Boolean
    if udt_name == "timestamp":
        return postgresql.TIMESTAMP
    if udt_name == "vector":
        return Vector
    return postgresql.ENUM


def test_sqlalchemy_maps_exactly_the_business_tables_and_association_table() -> None:
    from inkforge_core.db import models
    from inkforge_core.db.base import Base

    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert {name for name in EXPECTED_MODEL_TABLES if hasattr(models, name)} == (
        EXPECTED_MODEL_TABLES
    )
    assert not hasattr(models, "PrismaMigration")


def test_every_column_matches_the_frozen_contract() -> None:
    from inkforge_core.db.base import Base

    for table_name, expected_table in _business_contract_tables().items():
        actual_table = Base.metadata.tables[table_name]
        expected_columns = {column["name"]: column for column in expected_table["columns"]}
        actual_columns = {column.name: column for column in actual_table.columns}

        assert set(actual_columns) == set(expected_columns), table_name
        for column_name, expected in expected_columns.items():
            actual = actual_columns[column_name]
            assert isinstance(actual.type, _expected_python_type(expected["udtName"])), (
                table_name,
                column_name,
            )
            assert actual.nullable is expected["nullable"], (table_name, column_name)
            assert _server_default_sql(actual) == expected["default"], (
                table_name,
                column_name,
            )


def test_enums_use_exact_database_names_values_and_never_create_types() -> None:
    from inkforge_core.db.base import Base

    expected_enums = {item["name"]: item["values"] for item in _contract()["enums"]}
    actual_enums: dict[str, postgresql.ENUM] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, postgresql.ENUM):
                actual_enums[column.type.name] = column.type

    assert set(actual_enums) == set(expected_enums)
    for name, expected_values in expected_enums.items():
        enum = actual_enums[name]
        assert enum.enums == expected_values
        assert enum.create_type is False


def test_timestamp_text_bigint_and_vector_types_preserve_existing_storage() -> None:
    from inkforge_core.db.base import Base

    columns = [column for table in Base.metadata.tables.values() for column in table.columns]
    timestamp_columns = [
        column for column in columns if isinstance(column.type, postgresql.TIMESTAMP)
    ]
    bigint_columns = [column for column in columns if isinstance(column.type, BigInteger)]

    assert len(timestamp_columns) == 70
    assert all(column.type.precision == 3 for column in timestamp_columns)
    assert all(column.type.timezone is False for column in timestamp_columns)
    assert {(column.table.name, column.name) for column in bigint_columns} == {
        ("User", "creditBalanceMicros"),
        ("CreditLedger", "amountMicros"),
        ("CreditLedger", "balanceAfterMicros"),
    }
    assert all(
        isinstance(column.type, Text)
        for column in columns
        if column.name not in {"embedding"}
        and next(
            expected["udtName"]
            for expected in _business_contract_tables()[column.table.name]["columns"]
            if expected["name"] == column.name
        )
        == "text"
    )
    embedding = Base.metadata.tables["RagChunk"].c.embedding
    assert isinstance(embedding.type, Vector)
    assert embedding.type.dim is None
    assert not any(
        column.type.__class__.__name__ in {"JSON", "JSONB", "Numeric"} for column in columns
    )


def test_primary_keys_foreign_keys_and_indexes_match_the_frozen_contract() -> None:
    from inkforge_core.db.base import Base

    for table_name, expected_table in _business_contract_tables().items():
        table = Base.metadata.tables[table_name]
        expected_primary_key = expected_table["primaryKey"]
        assert table.primary_key.name == expected_primary_key["name"]
        assert [column.name for column in table.primary_key.columns] == expected_primary_key[
            "columns"
        ]

        actual_foreign_keys = {
            constraint.name: constraint for constraint in table.foreign_key_constraints
        }
        expected_foreign_keys = {
            constraint["name"]: constraint for constraint in expected_table["foreignKeys"]
        }
        assert set(actual_foreign_keys) == set(expected_foreign_keys), table_name
        for name, expected in expected_foreign_keys.items():
            actual = actual_foreign_keys[name]
            assert [element.parent.name for element in actual.elements] == expected["columns"]
            assert [element.target_fullname.split(".")[-1] for element in actual.elements] == (
                expected["targetColumns"]
            )
            assert {element.column.table.name for element in actual.elements} == {
                expected["targetTable"]
            }
            assert actual.ondelete == expected["onDelete"]
            assert actual.onupdate == expected["onUpdate"]

        expected_indexes = {
            index["name"]: index
            for index in expected_table["indexes"]
            if index["name"] != expected_primary_key["name"]
        }
        actual_indexes = {index.name: index for index in table.indexes}
        assert set(actual_indexes) == set(expected_indexes), table_name
        for name, expected in expected_indexes.items():
            actual = actual_indexes[name]
            assert actual.unique is expected["unique"]
            assert [column.name for column in actual.columns] == [
                item["column"] for item in expected["keyItems"]
            ]

        assert not table.constraints.difference({table.primary_key, *table.foreign_key_constraints})


def test_association_table_and_writing_message_reserved_attribute_are_exact() -> None:
    from inkforge_core.db.base import Base
    from inkforge_core.db.models import WritingMessage, faction_territories

    assert faction_territories is Base.metadata.tables["_FactionTerritories"]
    assert [column.name for column in faction_territories.primary_key.columns] == ["A", "B"]
    assert faction_territories.primary_key.name == "_FactionTerritories_AB_pkey"
    assert {index.name for index in faction_territories.indexes} == {"_FactionTerritories_B_index"}
    assert WritingMessage.metadata_.property.columns[0].name == "metadata"


def test_application_defaults_generate_compatible_ids_and_utc_naive_milliseconds() -> None:
    from inkforge_core.db.base import Base, generate_id, utc_now

    generated = {generate_id() for _ in range(100)}
    assert len(generated) == 100
    assert all(isinstance(identifier, str) and identifier for identifier in generated)

    now = utc_now()
    assert now.tzinfo is None
    assert now.microsecond % 1000 == 0
    assert abs((datetime.now(UTC).replace(tzinfo=None) - now).total_seconds()) < 1

    for table_name in EXPECTED_MODEL_TABLES:
        table = Base.metadata.tables[table_name]
        assert table.c.id.default is not None
        assert table.c.id.default.arg.__wrapped__ is generate_id
        if "updatedAt" in table.c:
            assert table.c.updatedAt.default is not None
            assert table.c.updatedAt.default.arg.__wrapped__ is utc_now
            assert table.c.updatedAt.onupdate is not None
            assert table.c.updatedAt.onupdate.arg.__wrapped__ is utc_now
            assert table.c.updatedAt.server_default is None


def test_runtime_source_contains_no_schema_mutation_capability() -> None:
    source_root = Path(__file__).parents[2] / "src" / "inkforge_core"
    files = list(source_root.rglob("*.py"))
    source = "\n".join(path.read_text("utf-8") for path in files)
    tree = ast.parse(source)

    assert ".create_all(" not in source
    assert ".drop_all(" not in source
    assert "alembic" not in source.lower()
    forbidden_calls = {"create", "drop", "alter"}
    assert not {
        node.func.attr.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.lower() in forbidden_calls
    }


def test_database_url_is_safely_normalized_for_asyncpg() -> None:
    from inkforge_core.db.session import normalize_database_url

    normalized = normalize_database_url(
        "postgresql://name:p%40ss%3Aword@database:5432/inkforge?sslmode=require"
    )

    url = cast(URL, normalized)
    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "name"
    assert url.password == "p@ss:word"  # noqa: S105
    assert url.database == "inkforge"
    assert url.query == {"sslmode": "require"}


def test_database_engine_uses_the_bounded_single_host_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkforge_core.db import session

    sentinel = cast(AsyncEngine, object())
    captured: dict[str, Any] = {}

    def fake_create_async_engine(url: URL, **kwargs: Any) -> AsyncEngine:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(session, "create_async_engine", fake_create_async_engine)

    engine = session.create_database_engine("postgresql://user:password@db/inkforge")

    assert engine is sentinel
    assert cast(URL, captured["url"]).drivername == "postgresql+asyncpg"
    assert captured["pool_size"] == 5
    assert captured["max_overflow"] == 0
    assert captured["pool_pre_ping"] is True


def test_session_factory_disables_implicit_expiration_and_autoflush() -> None:
    from inkforge_core.db.session import create_session_factory

    engine = cast(AsyncEngine, object())
    factory = create_session_factory(engine)

    assert factory.kw["bind"] is engine
    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["autoflush"] is False


class _ScalarResult:
    def scalar_one(self) -> int:
        return 1


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any) -> _ScalarResult:
        self.statements.append(str(statement))
        return _ScalarResult()


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection_instance = connection

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.connection_instance)


async def test_database_readiness_executes_only_select_one() -> None:
    from inkforge_core.db.session import check_database_connection

    connection = _Connection()
    ready = await check_database_connection(cast(AsyncEngine, _Engine(connection)))

    assert ready is True
    assert connection.statements == ["SELECT 1"]


def test_configured_database_registers_connection_and_schema_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkforge_core import app as app_module
    from inkforge_core.config import Settings
    from inkforge_core.db import session

    engine = cast(AsyncEngine, object())
    monkeypatch.setattr(session, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())

    app = app_module.create_app(
        settings=Settings.model_validate(
            {"environment": "dev", "database_url": "postgresql://user:secret@db/inkforge"}
        )
    )

    assert app.state.database_engine is engine
    assert set(app.state.readiness_checks) == {
        "configuration",
        "database",
        "database_schema",
    }


def test_database_readiness_failure_returns_generic_not_ready_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkforge_core import app as app_module
    from inkforge_core.config import Settings
    from inkforge_core.db import session

    opaque_marker = "do-not-leak-database-password"
    engine = cast(AsyncEngine, object())

    async def failed_connection(_engine: AsyncEngine) -> bool:
        raise RuntimeError(opaque_marker)

    async def failed_schema(_url: str, _path: Path) -> Any:
        raise RuntimeError(opaque_marker)

    monkeypatch.setattr(session, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(session, "check_database_connection", failed_connection)
    monkeypatch.setattr(session, "verify_live_schema", failed_schema)

    app = app_module.create_app(
        settings=Settings.model_validate(
            {
                "environment": "dev",
                "database_url": f"postgresql://user:{opaque_marker}@db/inkforge",
            }
        )
    )
    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "core-api",
        "checks": {
            "configuration": "ok",
            "database": "failed",
            "database_schema": "failed",
        },
    }
    assert opaque_marker not in response.text


def test_schema_drift_marks_only_schema_readiness_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkforge_core import app as app_module
    from inkforge_core.config import Settings
    from inkforge_core.db import session
    from inkforge_core.db.schema_guard import SchemaVerificationResult

    engine = cast(AsyncEngine, object())

    async def connected(_engine: AsyncEngine) -> bool:
        return True

    async def drifted(_url: str, _path: Path) -> SchemaVerificationResult:
        return SchemaVerificationResult(ready=False, fingerprint="drifted", diffs=[])

    monkeypatch.setattr(session, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(session, "check_database_connection", connected)
    monkeypatch.setattr(session, "verify_live_schema", drifted)

    app = app_module.create_app(
        settings=Settings.model_validate(
            {"environment": "dev", "database_url": "postgresql://user:secret@db/inkforge"}
        )
    )
    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "configuration": "ok",
        "database": "ok",
        "database_schema": "failed",
    }


class _DisposableEngine:
    def __init__(self) -> None:
        self.dispose_count = 0

    async def dispose(self) -> None:
        self.dispose_count += 1


def test_application_lifespan_disposes_database_pool_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkforge_core import app as app_module
    from inkforge_core.config import Settings
    from inkforge_core.db import session

    engine = _DisposableEngine()
    monkeypatch.setattr(
        session,
        "create_database_engine",
        lambda _url: cast(AsyncEngine, engine),
    )
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    app = app_module.create_app(
        settings=Settings.model_validate(
            {"environment": "dev", "database_url": "postgresql://user:secret@db/inkforge"}
        )
    )

    with TestClient(app):
        assert engine.dispose_count == 0

    assert engine.dispose_count == 1
