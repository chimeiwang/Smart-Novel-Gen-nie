from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from .json_types import JsonObject

if TYPE_CHECKING:
    from .runtime import CliRuntime

type InputMode = Literal["argv_tty", "json"]
type OutputMode = Literal["json", "jsonl"]
type FileOutputKind = Literal["none", "data_json", "primary_text"]
type JsonStream = Generator[JsonObject, None, int]
type CommandResult = JsonObject | JsonStream
type CommandHandler = Callable[["CliRuntime", JsonObject], CommandResult]


@dataclass(frozen=True, slots=True)
class FileOutputSpec:
    kind: FileOutputKind
    field: str | None = None
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    handler: CommandHandler
    inputMode: InputMode
    outputMode: OutputMode
    fileOutput: FileOutputSpec
    mutation: bool
    requiresIdentity: bool
    requiresClientRequestId: bool


def build_registry(specs: Iterable[CommandSpec]) -> dict[str, CommandSpec]:
    registry: dict[str, CommandSpec] = {}
    for spec in specs:
        _validate_spec(spec)
        if spec.name in registry:
            raise ValueError(f"命令名重复：{spec.name}")
        registry[spec.name] = spec
    return registry


def _validate_spec(spec: CommandSpec) -> None:
    if not spec.name or spec.name != spec.name.strip():
        raise ValueError("命令名不能为空或包含首尾空白")
    if spec.inputMode not in {"argv_tty", "json"}:
        raise ValueError(f"命令 {spec.name} 的输入模式无效")
    if spec.outputMode not in {"json", "jsonl"}:
        raise ValueError(f"命令 {spec.name} 的输出模式无效")
    if spec.fileOutput.kind not in {"none", "data_json", "primary_text"}:
        raise ValueError(f"命令 {spec.name} 的文件输出类型无效")

    if spec.fileOutput.kind == "primary_text":
        if not spec.fileOutput.field or not spec.fileOutput.media_type:
            raise ValueError(f"命令 {spec.name} 的主文本输出缺少字段或媒体类型")
    elif spec.fileOutput.field is not None or spec.fileOutput.media_type is not None:
        raise ValueError(f"命令 {spec.name} 的文件输出元数据与类型不匹配")

    if spec.outputMode == "jsonl" and spec.fileOutput.kind != "none":
        raise ValueError(f"流式命令 {spec.name} 不能声明文件输出")
    if spec.mutation and not spec.requiresIdentity:
        raise ValueError(f"写命令 {spec.name} 必须要求身份")
    if spec.requiresClientRequestId and not spec.mutation:
        raise ValueError(f"命令 {spec.name} 要求请求 ID 时必须声明为写命令")


def _default_specs() -> list[CommandSpec]:
    from .commands.auth import login, logout, whoami
    from .commands.long.artifacts import ARTIFACT_COMMAND_SPECS
    from .commands.long.chapters import CHAPTER_COMMAND_SPECS
    from .commands.long.knowledge import (
        get_artifact,
        get_lore,
        get_planning,
        get_quality_check,
        get_resources,
        list_artifacts,
        list_foreshadowings,
        list_outline_nodes,
    )
    from .commands.long.lore_entities import LORE_ENTITY_COMMAND_SPECS
    from .commands.long.lore_relationships import LORE_RELATIONSHIP_COMMAND_SPECS
    from .commands.long.novels import create_novel, save_summary
    from .commands.long.outline_nodes import OUTLINE_NODE_COMMAND_SPECS
    from .commands.long.planning_mutations import PLANNING_COMMAND_SPECS
    from .commands.long.quality import QUALITY_COMMAND_SPECS
    from .commands.long.read import (
        get_chapter,
        get_novel,
        get_session,
        list_chapters,
        list_sessions,
    )
    from .commands.long.read import (
        list_novels as list_long_novels,
    )
    from .commands.long.references import REFERENCE_COMMAND_SPECS
    from .commands.long.styles import STYLE_COMMAND_SPECS
    from .commands.long.task_mutations import TASK_MUTATION_COMMAND_SPECS
    from .commands.long.tasks import get_task, list_tasks
    from .commands.long.tasks import watch as watch_task
    from .commands.short.agents import (
        start as agent_start,
    )
    from .commands.short.agents import (
        watch as agent_watch,
    )
    from .commands.short.documents import (
        create as short_create,
    )
    from .commands.short.documents import (
        draft_save,
        list_novels,
        pull,
    )
    from .commands.short.versions import (
        adopt,
        diff,
        get,
        list_versions,
        preview,
        restore,
        submit,
    )

    no_file = FileOutputSpec(kind="none")
    data_json = FileOutputSpec(kind="data_json")
    primary_content = FileOutputSpec(
        kind="primary_text",
        field="content",
        media_type="text/plain; charset=utf-8",
    )

    def long_read_spec(
        name: str,
        handler: CommandHandler,
        file_output: FileOutputSpec = data_json,
    ) -> CommandSpec:
        return CommandSpec(
            name=name,
            handler=handler,
            inputMode="json",
            outputMode="json",
            fileOutput=file_output,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        )

    return [
        CommandSpec(
            name="auth.login",
            handler=login,
            inputMode="argv_tty",
            outputMode="json",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=False,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="auth.logout",
            handler=logout,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="auth.whoami",
            handler=whoami,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.list",
            handler=list_novels,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.create",
            handler=short_create,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=True,
        ),
        CommandSpec(
            name="short.pull",
            handler=pull,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.draft.save",
            handler=draft_save,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.version.preview",
            handler=preview,
            inputMode="json",
            outputMode="json",
            fileOutput=data_json,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.version.submit",
            handler=submit,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=True,
        ),
        CommandSpec(
            name="short.version.list",
            handler=list_versions,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.version.diff",
            handler=diff,
            inputMode="json",
            outputMode="json",
            fileOutput=data_json,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.version.get",
            handler=get,
            inputMode="json",
            outputMode="json",
            fileOutput=primary_content,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="short.version.adopt",
            handler=adopt,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=True,
        ),
        CommandSpec(
            name="short.version.restore",
            handler=restore,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=True,
        ),
        CommandSpec(
            name="short.agent.start",
            handler=agent_start,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=True,
        ),
        CommandSpec(
            name="short.agent.watch",
            handler=agent_watch,
            inputMode="json",
            outputMode="jsonl",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        long_read_spec("long.novel.list", list_long_novels),
        long_read_spec("long.novel.get", get_novel),
        CommandSpec(
            name="long.novel.create",
            handler=create_novel,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        CommandSpec(
            name="long.novel.summary.save",
            handler=save_summary,
            inputMode="json",
            outputMode="json",
            fileOutput=no_file,
            mutation=True,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        long_read_spec("long.chapter.list", list_chapters),
        long_read_spec("long.chapter.get", get_chapter, primary_content),
        long_read_spec("long.session.list", list_sessions),
        long_read_spec("long.session.get", get_session),
        long_read_spec("long.planning.get", get_planning),
        long_read_spec("long.lore.get", get_lore),
        long_read_spec("long.resources.get", get_resources),
        long_read_spec("long.outline-node.list", list_outline_nodes),
        long_read_spec("long.foreshadowing.list", list_foreshadowings),
        long_read_spec("long.task.list", list_tasks),
        long_read_spec("long.task.get", get_task),
        CommandSpec(
            name="long.task.watch",
            handler=watch_task,
            inputMode="json",
            outputMode="jsonl",
            fileOutput=no_file,
            mutation=False,
            requiresIdentity=True,
            requiresClientRequestId=False,
        ),
        long_read_spec("long.artifact.list", list_artifacts),
        long_read_spec("long.artifact.get", get_artifact),
        long_read_spec("long.quality.get", get_quality_check),
        *CHAPTER_COMMAND_SPECS,
        *TASK_MUTATION_COMMAND_SPECS,
        *ARTIFACT_COMMAND_SPECS,
        *QUALITY_COMMAND_SPECS,
        *PLANNING_COMMAND_SPECS,
        *OUTLINE_NODE_COMMAND_SPECS,
        *LORE_ENTITY_COMMAND_SPECS,
        *LORE_RELATIONSHIP_COMMAND_SPECS,
        *REFERENCE_COMMAND_SPECS,
        *STYLE_COMMAND_SPECS,
    ]


_REGISTRY: Mapping[str, CommandSpec] | None = None


def get_command_registry() -> Mapping[str, CommandSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = MappingProxyType(build_registry(_default_specs()))
    return _REGISTRY
