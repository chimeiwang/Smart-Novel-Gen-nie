from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from .updates import filter_agent_updates_by_selection

ApplyTarget = Literal[
    "agent_updates", "outline_content", "chapter_content", "beat_plan", "selection"
]


def resolve_apply_target(payload: dict[str, Any]) -> ApplyTarget | None:
    target = payload.get("target")
    if isinstance(target, dict) and target.get("mode") in {
        "replace_selection",
        "outline_content_selection",
        "outline_node_content_selection",
    }:
        if payload.get("kind") in {"chapter_draft", "outline_draft"}:
            return "selection"
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
    def payload(self) -> dict[str, Any]: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def chapter_id(self) -> str | None: ...


class FormalWritePort(Protocol):
    async def apply_selection(
        self, artifact: ApplicableArtifactPort, user_id: str, replacement: str
    ) -> int: ...

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
    async def apply(
        self,
        novel_id: str,
        user_id: str,
        updates: dict[str, object],
        *,
        expected_outline_updated_at: datetime | None = None,
    ) -> int: ...


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
        edited_replacement: str | None = None,
        selected_update_refs: list[dict[str, object]] | None,
    ) -> int:
        payload = artifact.payload
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
            expected_outline_updated_at = _optional_datetime(
                payload.get("baseOutlineUpdatedAt"),
                field="baseOutlineUpdatedAt",
            )
            return await self._updates_executor.apply(
                artifact.novel_id,
                user_id,
                updates,
                expected_outline_updated_at=expected_outline_updated_at,
            )

        if target == "selection":
            if edited_content is not None:
                raise ValueError("閫夊尯鑽夋涓嶅厑璁稿啀鎻愪緵 editedContent 鍏ㄦ枃鍐呭")
            replacement = (
                edited_replacement
                if edited_replacement is not None
                else payload.get("replacement")
            )
            if not isinstance(replacement, str) or not replacement.strip():
                raise ValueError("閫夊尯鑽夋缂哄皯闈炵┖ replacement")
            return await self._formal_writes.apply_selection(
                artifact, user_id, replacement
            )

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


def _optional_datetime(value: object, *, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} 必须是 ISO 8601 时间")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是 ISO 8601 时间") from exc
