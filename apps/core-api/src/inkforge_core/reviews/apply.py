from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Protocol

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
    def payload(self) -> dict[str, Any]: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def chapter_id(self) -> str | None: ...


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
    async def apply(
        self,
        novel_id: str,
        user_id: str,
        updates: dict[str, object],
        *,
        expected_outline_updated_at: datetime | None = None,
        expected_lore_updated_at: dict[str, datetime | None] | None = None,
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
            expected_lore_updated_at = _optional_datetime_map(
                payload.get("baseLoreUpdatedAt"),
                field="baseLoreUpdatedAt",
            )
            return await self._updates_executor.apply(
                artifact.novel_id,
                user_id,
                updates,
                expected_outline_updated_at=expected_outline_updated_at,
                expected_lore_updated_at=expected_lore_updated_at,
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
        normalized_beat_plan = _normalize_beat_plan(beat_plan)
        return await self._formal_writes.apply_beat_plan(
            artifact,
            user_id,
            normalized_beat_plan,
        )


def _normalize_beat_plan(beat_plan: dict[str, object]) -> dict[str, object]:
    scenes = beat_plan.get("sceneBeats")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("章节计划场景必须是非空列表")

    normalized_scenes = [
        _normalize_scene_beat(scene, index=index)
        for index, scene in enumerate(scenes)
    ]
    normalized_plan = dict(beat_plan)
    normalized_plan["sceneBeats"] = normalized_scenes
    return normalized_plan


def _normalize_scene_beat(scene: object, *, index: int) -> dict[str, object]:
    if not isinstance(scene, dict):
        raise ValueError("章节计划场景必须是对象")

    allowed_fields = {
        "order",
        "goal",
        "conflict",
        "characters",
        "foreshadowingRefs",
        "estimatedWords",
        "acceptanceCriteria",
        "sceneName",
        "sceneGoal",
        "foreshadowingReferences",
    }
    unknown_fields = set(scene) - allowed_fields
    if unknown_fields:
        raise ValueError(
            f"章节计划场景包含未知字段：{'、'.join(sorted(unknown_fields))}"
        )

    normalized = dict(scene)
    if "goal" in scene:
        goal = scene["goal"]
        if not isinstance(goal, str) or not goal:
            raise ValueError("章节计划场景 goal 必须是非空字符串")
        if "sceneName" in scene or "sceneGoal" in scene:
            raise ValueError(
                "章节计划场景不能同时包含 goal 与 sceneName/sceneGoal"
            )
    else:
        scene_name = scene.get("sceneName")
        scene_goal = scene.get("sceneGoal")
        if not isinstance(scene_name, str) or not scene_name.strip():
            raise ValueError("章节计划旧场景缺少有效 sceneName")
        if not isinstance(scene_goal, str) or not scene_goal.strip():
            raise ValueError("章节计划场景缺少有效 goal 或 sceneGoal")
        normalized["goal"] = f"{scene_name.strip()}：{scene_goal.strip()}"
        normalized.pop("sceneName", None)
        normalized.pop("sceneGoal", None)

    if "order" not in scene:
        normalized["order"] = index + 1
    else:
        order = scene["order"]
        if type(order) is not int or order < 1:
            raise ValueError("章节计划场景 order 必须是正整数")

    characters = scene.get("characters", [])
    if isinstance(characters, str):
        normalized["characters"] = [
            name.strip() for name in re.split(r"[、，,]", characters) if name.strip()
        ]
    else:
        normalized_characters = _normalize_string_list(
            characters,
            field="characters",
        )
        if "characters" not in scene:
            normalized["characters"] = normalized_characters

    if "foreshadowingRefs" in scene:
        if "foreshadowingReferences" in scene:
            raise ValueError(
                "章节计划场景不能同时包含 foreshadowingRefs "
                "与 foreshadowingReferences"
            )
        refs = scene["foreshadowingRefs"]
        if refs is not None:
            _normalize_string_list(refs, field="foreshadowingRefs")
    elif "foreshadowingReferences" in scene:
        legacy_refs = scene["foreshadowingReferences"]
        if not isinstance(legacy_refs, str):
            raise ValueError("章节计划旧场景 foreshadowingReferences 必须是字符串")
        normalized["foreshadowingRefs"] = [] if not legacy_refs.strip() else [legacy_refs]
        normalized.pop("foreshadowingReferences", None)

    estimated_words = scene.get("estimatedWords")
    if estimated_words is not None and (
        type(estimated_words) is not int or estimated_words < 0
    ):
        raise ValueError("章节计划场景 estimatedWords 必须是非负整数")

    conflict = scene.get("conflict")
    if conflict is not None and not isinstance(conflict, str):
        raise ValueError("章节计划场景 conflict 必须是字符串")

    acceptance_criteria = scene.get("acceptanceCriteria")
    if acceptance_criteria is not None and (
        not isinstance(acceptance_criteria, str) or not acceptance_criteria
    ):
        raise ValueError("章节计划场景 acceptanceCriteria 必须是非空字符串")

    return normalized


def _normalize_string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"章节计划场景 {field} 必须是字符串列表")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"章节计划场景 {field} 只能包含非空字符串")
    return value


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


def _optional_datetime_map(
    value: object,
    *,
    field: str,
) -> dict[str, datetime | None] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field} 必须是对象")
    allowed = {"worldSetting", "storyBackground"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{field} 包含未知字段：{'、'.join(sorted(unknown))}")
    return {
        key: _optional_datetime(item, field=f"{field}.{key}")
        for key, item in value.items()
    }
