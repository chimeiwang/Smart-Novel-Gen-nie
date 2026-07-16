from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterWritingGoal,
    Foreshadowing,
    Novel,
    OutlineNode,
    ReviewArtifact,
    SceneBeat,
    WritingRunCommand,
    WritingTask,
)
from ..errors import ApiError
from .recovery import InvalidGraphSnapshotError, deserialize_graph_snapshot


@dataclass(frozen=True, slots=True)
class ChapterGroupSnapshot:
    id: str
    title: str
    chapter_start_order: int
    chapter_end_order: int
    content: str
    parent_id: str | None = None


def select_unique_chapter_group(
    chapter_order: int, groups: list[ChapterGroupSnapshot]
) -> ChapterGroupSnapshot | None:
    matches = [
        group
        for group in groups
        if group.chapter_start_order <= chapter_order <= group.chapter_end_order
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ApiError(
            status_code=409,
            code="CHAPTER_GROUP_MAPPING_CONFLICT",
            message="当前章节没有唯一对应的章节组，不能调用写作模型",
        )
    return matches[0]


class PlanningContextPort(Protocol):
    async def get_planning_context(self, user_id: str, task_id: str) -> dict[str, Any]: ...


class WorkspaceContextPort(Protocol):
    async def get_workspace(self, novel_id: str, user_id: str, chapter_id: str | None) -> Any: ...


class WritingContextService:
    def __init__(self, planning: PlanningContextPort, workspace: WorkspaceContextPort) -> None:
        self._planning = planning
        self._workspace = workspace

    async def build(self, user_id: str, task_id: str) -> dict[str, Any]:
        planning = await self._planning.get_planning_context(user_id, task_id)
        workspace = await self._workspace.get_workspace(
            planning["novelId"], user_id, planning["chapterId"]
        )
        if isinstance(workspace, BaseModel):
            workspace_value = workspace.model_dump(mode="json")
        elif isinstance(workspace, dict):
            workspace_value = workspace
        else:
            raise TypeError("作品工作区聚合结果类型无效")
        return {"workspace": workspace_value, "planning": planning}


class WritingContextRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_binding(self, user_id: str, novel_id: str, task_id: str) -> None:
        async with self._session_factory() as session:
            found = await session.scalar(
                select(WritingTask.id)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(
                    WritingTask.id == task_id,
                    WritingTask.novelId == novel_id,
                    Novel.userId == user_id,
                )
            )
        if found is None:
            raise ApiError(
                status_code=403,
                code="WRITING_TASK_FORBIDDEN",
                message="写作任务资源绑定不匹配",
            )

    async def get_planning_context(self, user_id: str, task_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(WritingTask, Chapter.order)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .join(Chapter, Chapter.id == WritingTask.chapterId)
                    .where(WritingTask.id == task_id, Novel.userId == user_id)
                )
            ).one_or_none()
            if row is None:
                raise ApiError(
                    status_code=403,
                    code="WRITING_TASK_FORBIDDEN",
                    message="无权访问该写作任务",
                )
            task, chapter_order = row
            groups = await self._chapter_groups(session, task.novelId)
            group = select_unique_chapter_group(chapter_order, groups)
            goal = await session.scalar(
                select(ChapterWritingGoal)
                .where(ChapterWritingGoal.chapterId == task.chapterId)
                .order_by(ChapterWritingGoal.updatedAt.desc(), ChapterWritingGoal.id.desc())
                .limit(1)
            )
            beat_plan = await session.scalar(
                select(ChapterBeatPlan)
                .where(
                    ChapterBeatPlan.chapterId == task.chapterId,
                    ChapterBeatPlan.status == "approved",
                )
                .order_by(ChapterBeatPlan.updatedAt.desc(), ChapterBeatPlan.id.desc())
                .limit(1)
            )
            scenes: list[SceneBeat] = []
            if beat_plan is not None:
                scenes = list(
                    (
                        await session.execute(
                            select(SceneBeat)
                            .where(SceneBeat.beatPlanId == beat_plan.id)
                            .order_by(SceneBeat.order, SceneBeat.id)
                        )
                    ).scalars()
                )
            outline_path = await self._outline_path(session, group) if group is not None else []
            foreshadowing_summaries = await self._foreshadowing_summaries(
                session, task.novelId
            )
            active_artifact = await self._active_artifact(session, task)
            conversation_history = _conversation_history(task.conversationHistory)
            prior_conversation_history, latest_user_message = (
                _split_current_user_message(conversation_history)
            )
            return {
                "taskId": task.id,
                "novelId": task.novelId,
                "chapterId": task.chapterId,
                "chapterOrder": chapter_order,
                "chapterGoal": _goal_dict(goal),
                "approvedBeatPlan": _beat_plan_dict(beat_plan, scenes),
                "chapterGroup": (
                    {
                        "id": group.id,
                        "title": group.title,
                        "chapterStartOrder": group.chapter_start_order,
                        "chapterEndOrder": group.chapter_end_order,
                        "content": group.content,
                    }
                    if group is not None
                    else None
                ),
                "outlinePath": outline_path,
                "foreshadowingSummaries": foreshadowing_summaries,
                "activeArtifact": active_artifact,
                "phase": task.phase,
                "targetWordCount": task.targetWordCount,
                "selectedAgents": [item for item in task.selectedAgents.split(",") if item],
                "conversationHistory": prior_conversation_history,
                "userMessage": latest_user_message,
                "graphState": (json.loads(task.graphStateJson) if task.graphStateJson else None),
            }

    async def _chapter_groups(
        self, session: AsyncSession, novel_id: str
    ) -> list[ChapterGroupSnapshot]:
        nodes = list(
            (
                await session.execute(
                    select(OutlineNode).where(
                        OutlineNode.novelId == novel_id,
                        OutlineNode.kind == "chapter_group",
                    )
                )
            ).scalars()
        )
        return [
            ChapterGroupSnapshot(
                id=node.id,
                title=node.title,
                chapter_start_order=node.chapterStartOrder or 0,
                chapter_end_order=node.chapterEndOrder or 0,
                content=node.content or "",
                parent_id=node.parentId,
            )
            for node in nodes
        ]

    async def _foreshadowing_summaries(
        self,
        session: AsyncSession,
        novel_id: str,
    ) -> list[dict[str, Any]]:
        values = list(
            (
                await session.scalars(
                    select(Foreshadowing)
                    .where(Foreshadowing.novelId == novel_id)
                    .order_by(Foreshadowing.createdAt.asc(), Foreshadowing.id.asc())
                )
            ).all()
        )
        return [
            {
                "id": value.id,
                "name": value.name,
                "status": value.status,
                "plantedAt": value.plantedAt,
                "expectedPayoff": value.expectedPayoff,
                "payoffAt": value.payoffAt,
            }
            for value in values
        ]

    async def _outline_path(
        self, session: AsyncSession, group: ChapterGroupSnapshot
    ) -> list[dict[str, Any]]:
        path: list[dict[str, Any]] = []
        parent_id = group.parent_id
        while parent_id is not None:
            node = await session.get(OutlineNode, parent_id)
            if node is None:
                raise ApiError(
                    status_code=409,
                    code="OUTLINE_PARENT_MISSING",
                    message="章节组父级大纲节点不存在",
                )
            path.append(
                {
                    "id": node.id,
                    "kind": node.kind,
                    "title": node.title,
                    "chapterStartOrder": node.chapterStartOrder,
                    "chapterEndOrder": node.chapterEndOrder,
                }
            )
            parent_id = node.parentId
        path.reverse()
        return path

    async def _active_artifact(
        self, session: AsyncSession, task: WritingTask
    ) -> dict[str, Any] | None:
        if not task.graphStateJson:
            return None
        try:
            snapshot = deserialize_graph_snapshot(
                task.graphStateJson,
                expected_task_id=task.id,
                expected_novel_id=task.novelId,
                expected_chapter_id=task.chapterId,
            )
        except InvalidGraphSnapshotError:
            raise ApiError(
                status_code=409,
                code="WRITING_SNAPSHOT_INVALID",
                message="写作任务稳定快照格式错误",
            ) from None
        if snapshot.active_artifact_id is None:
            return None
        artifact = await session.scalar(
            select(ReviewArtifact).where(
                ReviewArtifact.id == snapshot.active_artifact_id,
                ReviewArtifact.taskId == task.id,
                ReviewArtifact.novelId == task.novelId,
            )
        )
        if artifact is not None and artifact.status in {
            "draft",
            "under_review",
            "awaiting_user",
            "applying",
        }:
            try:
                payload = json.loads(artifact.payloadJson)
                diff = json.loads(artifact.diffJson) if artifact.diffJson is not None else None
            except (json.JSONDecodeError, TypeError):
                raise _artifact_payload_invalid() from None
            if not isinstance(payload, dict) or payload.get("kind") != artifact.kind:
                raise _artifact_payload_invalid()
            return {
                "id": artifact.id,
                "taskId": artifact.taskId,
                "novelId": artifact.novelId,
                "chapterId": artifact.chapterId,
                "workflowRunId": artifact.workflowRunId,
                "artifactKey": artifact.artifactKey,
                "kind": artifact.kind,
                "status": artifact.status,
                "title": artifact.title,
                "summary": artifact.summary,
                "payload": payload,
                "diff": diff,
                "createdByAgent": artifact.createdByAgent,
                "reviewerAgent": artifact.reviewerAgent,
                "revision": artifact.revision,
            }
        active_decision_command = await session.scalar(
            select(WritingRunCommand.id).where(
                WritingRunCommand.taskId == task.id,
                WritingRunCommand.artifactId == snapshot.active_artifact_id,
                WritingRunCommand.kind == "artifact_decision",
                WritingRunCommand.status.in_(("pending", "submitted", "processing")),
            )
        )
        if active_decision_command is not None:
            return None
        raise ApiError(
            status_code=409,
            code="ACTIVE_ARTIFACT_MISMATCH",
            message="稳定快照引用的待审核草案与任务不匹配",
        )


def _artifact_payload_invalid() -> ApiError:
    return ApiError(
        status_code=409,
        code="ARTIFACT_PAYLOAD_INVALID",
        message="待审核草案的持久化内容格式无效",
    )


def _goal_dict(goal: ChapterWritingGoal | None) -> dict[str, Any] | None:
    if goal is None:
        return None
    return {
        "id": goal.id,
        "narrativeGoal": goal.narrativeGoal,
        "desiredEmotion": goal.desiredEmotion,
        "requiredForeshadowing": goal.requiredForeshadowing,
        "requiredCharacters": goal.requiredCharacters,
        "wordCountMin": goal.wordCountMin,
        "wordCountMax": goal.wordCountMax,
        "specialNotes": goal.specialNotes,
    }


def _conversation_history(serialized: str | None) -> list[dict[str, Any]]:
    if not serialized:
        return []
    try:
        value = json.loads(serialized)
    except json.JSONDecodeError:
        raise ApiError(
            status_code=409,
            code="WRITING_CONVERSATION_INVALID",
            message="写作任务对话历史格式错误",
        ) from None
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ApiError(
            status_code=409,
            code="WRITING_CONVERSATION_INVALID",
            message="写作任务对话历史格式错误",
        )
    return value


def _split_current_user_message(
    history: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    for index in range(len(history) - 1, -1, -1):
        item = history[index]
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            return [*history[:index], *history[index + 1 :]], str(item["content"])
    return list(history), ""


def _beat_plan_dict(plan: ChapterBeatPlan | None, scenes: list[SceneBeat]) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "chapterGoal": plan.chapterGoal,
        "mainPlotConnection": plan.mainPlotConnection,
        "chapterAcceptanceCriteria": plan.chapterAcceptanceCriteria,
        "totalEstimatedWords": plan.totalEstimatedWords,
        "generatedBy": plan.generatedBy,
        "sceneBeats": [
            {
                "id": scene.id,
                "order": scene.order,
                "goal": scene.goal,
                "conflict": scene.conflict,
                "characters": scene.characters,
                "foreshadowingRefs": scene.foreshadowingRefs,
                "estimatedWords": scene.estimatedWords,
                "acceptanceCriteria": scene.acceptanceCriteria,
            }
            for scene in scenes
        ],
    }
