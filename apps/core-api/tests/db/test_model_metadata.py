from __future__ import annotations

import ast
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import Any, cast, get_origin, get_type_hints

import pytest
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Integer, Text, create_engine, event, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import MANYTOMANY, ONETOMANY, Mapped, Session, configure_mappers

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
    "WritingRunCommand",
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


def _mapped_tables() -> dict[str, Any]:
    from inkforge_core.db.base import Base

    return {table.name: table for table in Base.metadata.tables.values()}


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


def _default_postgresql_opclass(column: Any) -> str:
    if isinstance(column.type, Text):
        return "text_ops"
    if isinstance(column.type, Integer):
        return "int4_ops"
    if isinstance(column.type, postgresql.TIMESTAMP):
        return "timestamp_ops"
    if isinstance(column.type, postgresql.ENUM):
        return "enum_ops"
    raise AssertionError(f"索引列类型没有已确认的 PostgreSQL 默认操作符类：{column.type}")


def _assert_index_key_defaults(column: Any, expected: dict[str, Any]) -> None:
    assert expected["kind"] == "column"
    assert expected["expression"] is None
    assert expected["column"] == column.name
    assert expected["opclassSchema"] == "pg_catalog"
    assert expected["opclass"] == _default_postgresql_opclass(column)
    if isinstance(column.type, Text):
        assert expected["collationSchema"] == "pg_catalog"
        assert expected["collation"] == "default"
    else:
        assert expected["collationSchema"] is None
        assert expected["collation"] is None
    assert expected["order"] == "ASC"
    assert expected["nulls"] == "LAST"


def test_sqlalchemy_maps_exactly_the_business_tables_and_association_table() -> None:
    from inkforge_core.db import models
    from inkforge_core.db.base import Base

    assert {table.name for table in Base.metadata.tables.values()} == EXPECTED_TABLES
    assert {table.schema for table in Base.metadata.tables.values()} == {"public"}
    assert {name for name in EXPECTED_MODEL_TABLES if hasattr(models, name)} == (
        EXPECTED_MODEL_TABLES
    )
    assert not hasattr(models, "PrismaMigration")


def test_every_column_matches_the_frozen_contract() -> None:

    for table_name, expected_table in _business_contract_tables().items():
        actual_table = _mapped_tables()[table_name]
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

    assert len(timestamp_columns) == 75
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
    embedding = _mapped_tables()["RagChunk"].c.embedding
    assert isinstance(embedding.type, Vector)
    assert embedding.type.dim is None
    assert not any(
        column.type.__class__.__name__ in {"JSON", "JSONB", "Numeric"} for column in columns
    )


def test_primary_keys_foreign_keys_and_indexes_match_the_frozen_contract() -> None:

    for table_name, expected_table in _business_contract_tables().items():
        table = _mapped_tables()[table_name]
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
            assert {element.column.table.schema for element in actual.elements} == {"public"}
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
            actual_columns = list(actual.columns)
            assert [column.name for column in actual_columns] == [
                item["column"] for item in expected["keyItems"]
            ]
            postgresql_options = actual.dialect_options["postgresql"]
            assert (postgresql_options["using"] or "btree") == expected["method"]
            assert (postgresql_options["ops"] or {}) == {}
            assert (postgresql_options["with"] or {}) == {}
            assert postgresql_options["tablespace"] is expected["tablespace"] is None
            if expected["predicate"] is None:
                assert postgresql_options["where"] is None
            else:
                predicate = str(postgresql_options["where"])
                assert '"status"' in predicate
                assert all(
                    value in predicate for value in ("pending", "submitted", "processing")
                )
            assert expected["includeColumns"] == []
            assert expected["options"] == []
            assert expected["nullsNotDistinct"] is False
            for column, key_item in zip(actual_columns, expected["keyItems"], strict=True):
                _assert_index_key_defaults(column, key_item)

        primary_index = next(
            index
            for index in expected_table["indexes"]
            if index["name"] == expected_primary_key["name"]
        )
        assert primary_index["method"] == "btree"
        assert primary_index["options"] == []
        assert primary_index["tablespace"] is None
        for column, key_item in zip(
            table.primary_key.columns,
            primary_index["keyItems"],
            strict=True,
        ):
            _assert_index_key_defaults(column, key_item)

        assert not table.constraints.difference({table.primary_key, *table.foreign_key_constraints})


def test_association_table_and_writing_message_reserved_attribute_are_exact() -> None:
    from inkforge_core.db.models import WritingMessage, faction_territories

    assert faction_territories is _mapped_tables()["_FactionTerritories"]
    assert [column.name for column in faction_territories.primary_key.columns] == ["A", "B"]
    assert faction_territories.primary_key.name == "_FactionTerritories_AB_pkey"
    assert {index.name for index in faction_territories.indexes} == {"_FactionTerritories_B_index"}
    assert WritingMessage.metadata_.property.columns[0].name == "metadata"


def test_writing_command_and_private_style_metadata() -> None:
    from inkforge_core.db import models

    assert hasattr(models, "WritingRunCommand")
    command = models.WritingRunCommand.__table__
    style = models.WritingStyle.__table__
    portrait = models.StylePortraitTask.__table__

    assert "WritingRunCommand_idempotencyKey_key" in {
        index.name for index in command.indexes if index.unique
    }
    assert style.c.userId.nullable is False
    assert next(iter(style.c.userId.foreign_keys)).target_fullname == "public.User.id"
    assert portrait.c.section.nullable is True


def test_application_defaults_generate_compatible_ids_and_utc_naive_milliseconds() -> None:
    from inkforge_core.db.base import generate_id, utc_now

    generated = {generate_id() for _ in range(100)}
    assert len(generated) == 100
    assert all(re.fullmatch(r"c[0-9a-z]{24}", identifier) for identifier in generated)
    current_milliseconds = int(time() * 1000)
    assert all(
        abs(int(identifier[1:9], 36) - current_milliseconds) < 5_000 for identifier in generated
    )

    now = utc_now()
    assert now.tzinfo is None
    assert now.microsecond % 1000 == 0
    assert abs((datetime.now(UTC).replace(tzinfo=None) - now).total_seconds()) < 1

    for table_name in EXPECTED_MODEL_TABLES:
        table = _mapped_tables()[table_name]
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
    from inkforge_core.db.url import asyncpg_connection_options

    options = asyncpg_connection_options(
        "postgresql://name:p%40ss%3Aword@database:5432/inkforge?sslmode=require&application_name=core-api"
    )

    url = options.url
    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "name"
    assert url.password == "p@ss:word"  # noqa: S105
    assert url.database == "inkforge"
    assert url.query == {}
    assert options.connect_args == {
        "ssl": "require",
        "server_settings": {"application_name": "core-api"},
    }


def test_database_engine_uses_the_bounded_single_host_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkforge_core.db import session

    sentinel = cast(AsyncEngine, object())
    captured: dict[str, Any] = {}

    def fake_create_async_engine(url: URL, **kwargs: Any) -> AsyncEngine:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(session, "create_async_engine", fake_create_async_engine)

    engine = session.create_database_engine(
        "postgresql://user:password@db/inkforge?sslmode=verify-full&application_name=core-api"
    )

    assert engine is sentinel
    captured_url = cast(URL, captured["url"])
    assert captured_url.drivername == "postgresql+asyncpg"
    assert captured_url.query == {}
    assert captured["connect_args"] == {
        "ssl": "verify-full",
        "server_settings": {"application_name": "core-api"},
    }
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

    async def failed_schema(_engine: AsyncEngine, _path: Path) -> Any:
        raise RuntimeError(opaque_marker)

    monkeypatch.setattr(session, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(session, "check_database_connection", failed_connection)
    monkeypatch.setattr(session, "verify_live_schema_with_engine", failed_schema)

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

    async def drifted(_engine: AsyncEngine, _path: Path) -> SchemaVerificationResult:
        return SchemaVerificationResult(ready=False, fingerprint="drifted", diffs=[])

    monkeypatch.setattr(session, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(session, "check_database_connection", connected)
    monkeypatch.setattr(session, "verify_live_schema_with_engine", drifted)

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


def test_application_lifespan_prewarms_database_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkforge_core import app as app_module
    from inkforge_core.config import Settings
    from inkforge_core.db import session

    engine = _DisposableEngine()
    warm_up_count = 0

    async def record_warm_up(_self: object) -> None:
        nonlocal warm_up_count
        warm_up_count += 1

    monkeypatch.setattr(
        session,
        "create_database_engine",
        lambda _url: cast(AsyncEngine, engine),
    )
    monkeypatch.setattr(session, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(session.DatabaseReadiness, "warm_up", record_warm_up)
    app = app_module.create_app(
        settings=Settings.model_validate(
            {"environment": "dev", "database_url": "postgresql://user:secret@db/inkforge"}
        )
    )

    with TestClient(app):
        assert warm_up_count == 1

    assert engine.dispose_count == 1


def test_all_model_columns_are_static_mapped_attributes() -> None:
    from inkforge_core.db import models

    for table_name, contract in _business_contract_tables().items():
        if table_name == "_FactionTerritories":
            continue
        model = getattr(models, table_name)
        annotations = get_type_hints(model)
        expected_attributes = {
            "metadata_" if column["name"] == "metadata" else column["name"]
            for column in contract["columns"]
        }
        assert expected_attributes <= set(annotations), table_name
        assert all(get_origin(annotations[name]) is Mapped for name in expected_attributes)

    assert models.User.id.key == "id"
    assert models.User.username.key == "username"
    assert models.WritingMessage.metadata_.key == "metadata_"


def test_mappers_cover_every_real_foreign_key_without_logical_id_relationships() -> None:
    from inkforge_core.db import models

    configure_mappers()
    mapped_models = [getattr(models, name) for name in EXPECTED_MODEL_TABLES]
    relationship_count = sum(len(inspect(model).relationships) for model in mapped_models)

    assert relationship_count == 114
    assert set(inspect(models.CharacterRelation).relationships.keys()) == {"character", "target"}
    assert inspect(models.Location).relationships["parent"].remote_side == {
        models.Location.__table__.c.id
    }
    assert inspect(models.OutlineNode).relationships["parent"].remote_side == {
        models.OutlineNode.__table__.c.id
    }
    assert inspect(models.Faction).relationships["territories"].secondary is (
        models.faction_territories
    )
    assert inspect(models.Location).relationships["factions"].secondary is (
        models.faction_territories
    )
    assert "user" not in inspect(models.WorkflowRun).relationships
    assert "chapter" not in inspect(models.WorkflowRun).relationships
    assert "chapter" not in inspect(models.CharacterStateChange).relationships


def test_parent_relationship_delete_policy_matches_every_real_foreign_key() -> None:
    from inkforge_core.db import models

    configure_mappers()
    parent_relationships = 0
    for model_name in EXPECTED_MODEL_TABLES:
        for relation in inspect(getattr(models, model_name)).relationships:
            if relation.direction is MANYTOMANY:
                assert relation.passive_deletes is True
                assert "delete" not in relation.cascade
                assert "delete-orphan" not in relation.cascade
                continue
            if relation.direction is not ONETOMANY:
                continue
            parent_relationships += 1
            on_delete = {
                foreign_key.ondelete
                for column in relation._calculated_foreign_keys
                for foreign_key in column.foreign_keys
            }
            assert len(on_delete) == 1, (model_name, relation.key)
            assert relation.passive_deletes is True, (model_name, relation.key)
            if on_delete == {"CASCADE"}:
                assert "delete" in relation.cascade, (model_name, relation.key)
            else:
                assert on_delete == {"SET NULL"}, (model_name, relation.key)
                assert "delete" not in relation.cascade, (model_name, relation.key)
            assert "delete-orphan" not in relation.cascade, (model_name, relation.key)

    assert parent_relationships == 56


def _sqlite_uow_engine(*tables: Any) -> Any:
    from inkforge_core.db.base import Base

    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={"schema_translate_map": {"public": None}},
    )
    Base.metadata.create_all(engine, tables=list(tables))
    return engine


@pytest.mark.parametrize("loaded", [True, False])
def test_cascade_parent_delete_never_sets_child_foreign_key_to_null(loaded: bool) -> None:
    from inkforge_core.db.models import CreditLedger, User

    engine = _sqlite_uow_engine(User.__table__, CreditLedger.__table__)
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _parameters, _context, _many: statements.append(
            statement
        ),
    )
    with Session(engine, expire_on_commit=False) as session:
        user = User(username=f"级联删除-{loaded}", passwordHash="内存测试")
        ledger = CreditLedger(
            type="test",
            amountMicros=1,
            balanceAfterMicros=1,
            userId=user.id,
        )
        user.creditLedgerEntries.append(ledger)
        session.add(user)
        session.flush()
        identifier = user.id
        if loaded:
            assert user.creditLedgerEntries == [ledger]
        else:
            session.expunge_all()
            user = session.get(User, identifier)
            assert user is not None
        statements.clear()

        session.delete(user)
        session.flush()

        normalized = [statement.upper() for statement in statements]
        assert not any(
            statement.startswith("UPDATE ") and '"CREDITLEDGER"' in statement
            for statement in normalized
        )
        assert not any('"USERID"=NULL' in statement.replace(" ", "") for statement in normalized)
        if loaded:
            assert any(
                statement.startswith("DELETE FROM ") and '"CREDITLEDGER"' in statement
                for statement in normalized
            ), normalized
        else:
            assert not any('CREDITLEDGER' in statement for statement in normalized)
        session.rollback()
    engine.dispose()


@pytest.mark.parametrize("loaded", [True, False])
def test_set_null_parent_delete_uses_orm_only_for_loaded_children(loaded: bool) -> None:
    from inkforge_core.db.models import Novel, User

    engine = _sqlite_uow_engine(User.__table__, Novel.__table__)
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _parameters, _context, _many: statements.append(
            statement
        ),
    )
    with Session(engine, expire_on_commit=False) as session:
        user = User(username=f"置空删除-{loaded}", passwordHash="内存测试")
        novel = Novel(name="内存测试小说", userId=user.id)
        user.novels.append(novel)
        session.add(user)
        session.flush()
        identifier = user.id
        if loaded:
            assert user.novels == [novel]
        else:
            session.expunge_all()
            user = session.get(User, identifier)
            assert user is not None
        statements.clear()

        session.delete(user)
        session.flush()

        normalized = [statement.upper() for statement in statements]
        assert not any(
            statement.startswith("DELETE FROM ") and '"NOVEL"' in statement
            for statement in normalized
        )
        if loaded:
            assert any(
                statement.startswith("UPDATE ") and '"NOVEL"' in statement
                for statement in normalized
            ), normalized
            assert novel.userId is None
        else:
            assert not any('NOVEL' in statement for statement in normalized)
        session.rollback()
    engine.dispose()


def test_cuid_generator_is_unique_under_thread_contention() -> None:
    from inkforge_core.db.base import generate_id

    with ThreadPoolExecutor(max_workers=32) as executor:
        identifiers = list(executor.map(lambda _index: generate_id(), range(10_000)))

    assert len(set(identifiers)) == len(identifiers)
    assert all(re.fullmatch(r"c[0-9a-z]{24}", identifier) for identifier in identifiers)


def test_model_instance_receives_cuid_before_flush() -> None:
    from inkforge_core.db.models import User

    user = User(username="静态类型测试", passwordHash="仅用于对象构造")

    assert re.fullmatch(r"c[0-9a-z]{24}", user.id)


@pytest.mark.parametrize(
    ("sslmode", "ssl"),
    [
        ("disable", "disable"),
        ("allow", "allow"),
        ("prefer", "prefer"),
        ("require", "require"),
        ("verify-ca", "verify-ca"),
        ("verify-full", "verify-full"),
    ],
)
def test_libpq_sslmode_is_translated_to_asyncpg_ssl(sslmode: str, ssl: str) -> None:
    from inkforge_core.db.url import asyncpg_connection_options

    options = asyncpg_connection_options(
        f"postgresql://user:credential@database/inkforge?application_name=core&sslmode={sslmode}"
    )

    assert options.url.query == {}
    assert options.connect_args == {
        "ssl": ssl,
        "server_settings": {"application_name": "core"},
    }


def test_invalid_sslmode_does_not_echo_the_database_url() -> None:
    from inkforge_core.db.url import asyncpg_connection_options

    marker = "sensitive-invalid-mode"
    with pytest.raises(ValueError) as caught:
        asyncpg_connection_options(
            f"postgresql://user:credential@database/inkforge?sslmode={marker}"
        )

    assert marker not in str(caught.value)
    assert "credential" not in str(caught.value)


def test_unknown_asyncpg_query_parameter_is_rejected_without_echo() -> None:
    from inkforge_core.db.url import asyncpg_connection_options

    marker = "sensitive-unknown-value"
    with pytest.raises(ValueError) as caught:
        asyncpg_connection_options(
            f"postgresql://user:credential@database/inkforge?connect_timeout={marker}"
        )

    assert marker not in str(caught.value)
    assert "credential" not in str(caught.value)


def test_database_package_does_not_expose_incomplete_url_only_api() -> None:
    import inkforge_core.db as database_package
    from inkforge_core.db import url

    assert not hasattr(database_package, "normalize_database_url")
    assert not hasattr(url, "normalize_database_url")


async def test_schema_readiness_reuses_main_pool_and_coalesces_concurrent_probes() -> None:
    from inkforge_core.db.schema_guard import SchemaVerificationResult
    from inkforge_core.db.session import DatabaseReadiness

    engine = cast(AsyncEngine, object())
    clock = [0.0]
    calls: list[AsyncEngine] = []

    async def verifier(
        received_engine: AsyncEngine, _contract_path: Path
    ) -> SchemaVerificationResult:
        calls.append(received_engine)
        await asyncio.sleep(0)
        return SchemaVerificationResult(ready=True, fingerprint="exact", diffs=[])

    readiness = DatabaseReadiness(
        engine,
        CONTRACT_PATH,
        schema_verifier=verifier,
        monotonic_clock=lambda: clock[0],
    )

    results = await asyncio.gather(*(readiness.check_schema() for _ in range(20)))
    assert results == [True] * 20
    assert calls == [engine]

    clock[0] = 29.0
    assert await readiness.check_schema() is True
    assert calls == [engine]

    clock[0] = 31.0
    assert await readiness.check_schema() is True
    assert calls == [engine, engine]


async def test_failed_schema_readiness_recovers_after_short_cache_period() -> None:
    from inkforge_core.db.schema_guard import SchemaVerificationResult
    from inkforge_core.db.session import DatabaseReadiness

    engine = cast(AsyncEngine, object())
    clock = [0.0]
    calls = 0

    async def verifier(_engine: AsyncEngine, _contract_path: Path) -> SchemaVerificationResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SchemaVerificationResult(ready=False, fingerprint="drifted", diffs=[])
        return SchemaVerificationResult(ready=True, fingerprint="recovered", diffs=[])

    readiness = DatabaseReadiness(
        engine,
        CONTRACT_PATH,
        schema_verifier=verifier,
        monotonic_clock=lambda: clock[0],
    )

    assert await readiness.check_schema() is False
    clock[0] = 4.0
    assert await readiness.check_schema() is False
    assert calls == 1
    clock[0] = 6.0
    assert await readiness.check_schema() is True
    assert calls == 2


def test_models_do_not_parse_the_schema_contract_dynamically() -> None:
    models_path = Path(__file__).parents[2] / "src" / "inkforge_core" / "db" / "models.py"
    source = models_path.read_text("utf-8")

    assert "json.loads" not in source
    assert "_build_table" not in source
