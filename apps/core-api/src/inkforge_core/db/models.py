from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects import postgresql

from .base import Base, generate_id, utc_now

_CONTRACT_PATH = Path(__file__).with_name("schema-contract.json")


def _load_contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_CONTRACT_PATH.read_text("utf-8")))


_CONTRACT = _load_contract()
_TABLE_CONTRACTS: dict[str, dict[str, Any]] = {
    str(table["name"]): cast(dict[str, Any], table) for table in _CONTRACT["tables"]
}
_ENUM_VALUES: dict[str, list[str]] = {
    str(enum["name"]): cast(list[str], enum["values"]) for enum in _CONTRACT["enums"]
}


def _column_type(column: dict[str, Any]) -> Any:
    udt_name = str(column["udtName"])
    if udt_name == "text":
        return Text()
    if udt_name == "int4":
        return Integer()
    if udt_name == "int8":
        return BigInteger()
    if udt_name == "bool":
        return Boolean()
    if udt_name == "timestamp":
        return postgresql.TIMESTAMP(precision=3, timezone=False)
    if udt_name == "vector":
        return Vector()
    if udt_name in _ENUM_VALUES:
        return postgresql.ENUM(
            *_ENUM_VALUES[udt_name],
            name=udt_name,
            create_type=False,
        )
    raise ValueError(f"数据库结构契约包含不受支持的列类型：{udt_name}")


def _column_foreign_keys(table_contract: dict[str, Any], column_name: str) -> list[ForeignKey]:
    foreign_keys: list[ForeignKey] = []
    for foreign_key in table_contract["foreignKeys"]:
        columns = cast(list[str], foreign_key["columns"])
        if columns != [column_name]:
            continue
        target_columns = cast(list[str], foreign_key["targetColumns"])
        foreign_keys.append(
            ForeignKey(
                f"{foreign_key['targetTable']}.{target_columns[0]}",
                name=str(foreign_key["name"]),
                ondelete=str(foreign_key["onDelete"]),
                onupdate=str(foreign_key["onUpdate"]),
            )
        )
    return foreign_keys


def _build_column(table_contract: dict[str, Any], column: dict[str, Any]) -> Column[Any]:
    name = str(column["name"])
    arguments: list[Any] = [_column_type(column)]
    arguments.extend(_column_foreign_keys(table_contract, name))
    keyword_arguments: dict[str, Any] = {
        "nullable": bool(column["nullable"]),
    }
    server_default = column["default"]
    if server_default is not None:
        keyword_arguments["server_default"] = text(str(server_default))
    if name == "id":
        keyword_arguments["default"] = generate_id
    elif name == "createdAt":
        keyword_arguments["default"] = utc_now
    elif name == "updatedAt":
        keyword_arguments["default"] = utc_now
        keyword_arguments["onupdate"] = utc_now
    if table_contract["name"] == "WritingMessage" and name == "metadata":
        keyword_arguments["key"] = "metadata_"
    return Column(name, *arguments, **keyword_arguments)


def _build_table(name: str) -> Table:
    contract = _TABLE_CONTRACTS[name]
    columns = [
        _build_column(contract, cast(dict[str, Any], column)) for column in contract["columns"]
    ]
    primary_key = cast(dict[str, Any], contract["primaryKey"])
    table = Table(
        name,
        Base.metadata,
        *columns,
        PrimaryKeyConstraint(
            *cast(list[str], primary_key["columns"]),
            name=str(primary_key["name"]),
        ),
    )
    for index_contract in contract["indexes"]:
        if index_contract["name"] == primary_key["name"]:
            continue
        column_names = [
            str(item["column"]) for item in index_contract["keyItems"] if item["kind"] == "column"
        ]
        Index(
            str(index_contract["name"]),
            *(table.c[column_name] for column_name in column_names),
            unique=bool(index_contract["unique"]),
        )
    return table


class User(Base):
    __table__ = _build_table("User")


class WritingStyle(Base):
    __table__ = _build_table("WritingStyle")


class Novel(Base):
    __table__ = _build_table("Novel")


class Chapter(Base):
    __table__ = _build_table("Chapter")


class ChapterQualityCheck(Base):
    __table__ = _build_table("ChapterQualityCheck")


class ChapterProgress(Base):
    __table__ = _build_table("ChapterProgress")


class Location(Base):
    __table__ = _build_table("Location")


class Faction(Base):
    __table__ = _build_table("Faction")


class Character(Base):
    __table__ = _build_table("Character")


class CharacterRelation(Base):
    __table__ = _build_table("CharacterRelation")


class CharacterExperience(Base):
    __table__ = _build_table("CharacterExperience")


class Item(Base):
    __table__ = _build_table("Item")


class Glossary(Base):
    __table__ = _build_table("Glossary")


class StoryBackground(Base):
    __table__ = _build_table("StoryBackground")


class WorldSetting(Base):
    __table__ = _build_table("WorldSetting")


class WritingBible(Base):
    __table__ = _build_table("WritingBible")


class Outline(Base):
    __table__ = _build_table("Outline")


class PlotProgress(Base):
    __table__ = _build_table("PlotProgress")


class ReferenceMaterial(Base):
    __table__ = _build_table("ReferenceMaterial")


class RagDocument(Base):
    __table__ = _build_table("RagDocument")


class RagChunk(Base):
    __table__ = _build_table("RagChunk")


class StyleReference(Base):
    __table__ = _build_table("StyleReference")


class StylePortraitTask(Base):
    __table__ = _build_table("StylePortraitTask")


class Foreshadowing(Base):
    __table__ = _build_table("Foreshadowing")


class OutlineNode(Base):
    __table__ = _build_table("OutlineNode")


class CharacterStateChange(Base):
    __table__ = _build_table("CharacterStateChange")


class WritingConfig(Base):
    __table__ = _build_table("WritingConfig")


class WritingSession(Base):
    __table__ = _build_table("WritingSession")


class WritingTask(Base):
    __table__ = _build_table("WritingTask")


class WritingMessage(Base):
    __table__ = _build_table("WritingMessage")


class TokenUsage(Base):
    __table__ = _build_table("TokenUsage")


class CreditLedger(Base):
    __table__ = _build_table("CreditLedger")


class WorkflowRun(Base):
    __table__ = _build_table("WorkflowRun")


class WorkflowStep(Base):
    __table__ = _build_table("WorkflowStep")


class ReviewArtifact(Base):
    __table__ = _build_table("ReviewArtifact")


class ReviewArtifactRevision(Base):
    __table__ = _build_table("ReviewArtifactRevision")


class ReviewArtifactEvaluation(Base):
    __table__ = _build_table("ReviewArtifactEvaluation")


class ChapterWritingGoal(Base):
    __table__ = _build_table("ChapterWritingGoal")


class ChapterBeatPlan(Base):
    __table__ = _build_table("ChapterBeatPlan")


class SceneBeat(Base):
    __table__ = _build_table("SceneBeat")


faction_territories = _build_table("_FactionTerritories")
