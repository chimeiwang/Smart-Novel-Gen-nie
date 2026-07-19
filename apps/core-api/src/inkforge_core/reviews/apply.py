from __future__ import annotations

from typing import Any, Literal, Protocol

from ..errors import ApiError
from .updates import filter_agent_updates_by_selection

ApplyTarget = Literal["agent_updates", "outline_content", "chapter_content", "beat_plan"]


def resolve_apply_target(payload: dict[str, Any]) -> ApplyTarget | None:
    kind = payload.get("kind")
    if kind == "agent_updates":
        return "agent_updates"
    if kind == "outline_draft":
        return "outline_content"
    if kind in {"chapter_content", "chapter_draft"}:
        return "chapter_content"
    if kind in {"beat_plan", "beat_plan_draft"}:
        return "beat_plan"
    return None


class ApplicableArtifactPort(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def payload(self) -> dict[str, Any]: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def chapter_id(self) -> str | None: ...

    @property
    def task_id(self) -> str | None: ...

    @property
    def revision(self) -> int: ...


class FormalWritePort(Protocol):
    async def apply_outline(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int: ...

    async def apply_chapter(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int: ...

    async def apply_beat_plan(
        self,
        artifact: ApplicableArtifactPort,
        user_id: str,
        beat_plan: dict[str, object],
    ) -> int: ...


class AgentUpdatesApplyPort(Protocol):
    async def apply(self, novel_id: str, user_id: str, updates: dict[str, object]) -> int: ...


class FormalArtifactApplier:
    def __init__(
        self, formal_writes: FormalWritePort, updates_executor: AgentUpdatesApplyPort
    ) -> None:
        self._formal_writes = formal_writes
        self._updates_executor = updates_executor

    async def apply(
        self,
        artifact: ApplicableArtifactPort,
        *,
        user_id: str,
        edited_content: str | None,
        selected_update_refs: list[dict[str, object]] | None,
    ) -> int:
        payload = artifact.payload
        if (
            payload.get("kind") == "chapter_draft"
            and payload.get("storyLengthProfile") == "short_medium"
            and (edited_content is not None or selected_update_refs is not None)
        ):
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_DRAFT_DIRECT_EDIT_FORBIDDEN",
                message="中短篇完整正文必须按当前精确版本批准，不能在批准时直接改写或部分应用",
            )
        target = resolve_apply_target(payload)
        if target is None:
            raise ValueError("该草案类型不能写入正式数据")
        if target == "agent_updates":
            raw_updates = payload.get("updates")
            if not isinstance(raw_updates, dict):
                raise ValueError("agent_updates 草案缺少结构化更新")
            updates = filter_agent_updates_by_selection(
                raw_updates,
                selected_update_refs,
            )
            if not updates:
                raise ValueError("没有选择任何可应用更新")
            return await self._updates_executor.apply(artifact.novel_id, user_id, updates)

        content = edited_content if edited_content is not None else payload.get("content")
        if target in {"outline_content", "chapter_content"}:
            if not isinstance(content, str) or not content:
                raise ValueError("文本草案缺少完整内容")
            if target == "outline_content":
                return await self._formal_writes.apply_outline(artifact, user_id, content)
            return await self._formal_writes.apply_chapter(artifact, user_id, content)

        beat_plan = payload.get("beatPlan")
        if payload.get("kind") == "beat_plan_draft":
            if not isinstance(content, str) or not content:
                raise ValueError("章节计划草案缺少完整内容")
            beat_plan = _beat_plan_from_text(content)
        if not isinstance(beat_plan, dict):
            raise ValueError("章节计划草案结构无效")
        return await self._formal_writes.apply_beat_plan(artifact, user_id, beat_plan)


def _beat_plan_from_text(content: str) -> dict[str, object]:
    return {
        "title": "章节计划草案",
        "summary": content,
        "chapterGoal": content,
        "totalEstimatedWords": 0,
        "sceneBeats": [
            {
                "order": 1,
                "goal": content,
                "characters": [],
                "estimatedWords": 0,
                "acceptanceCriteria": "按完整文本草案执行，并在写作前由作者确认细化。",
            }
        ],
    }
