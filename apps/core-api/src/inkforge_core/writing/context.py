from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from inkforge_contracts.jobs import (
    ApprovedShortOutlineSource,
    ShortOutlineInspirationSource,
    WritingJobPayload,
)
from inkforge_contracts.short_story import (
    ShortStoryChapterDraft,
    ShortStoryOutlineDraft,
    canonical_short_outline_hash,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import content_sha256
from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterWritingGoal,
    Foreshadowing,
    Novel,
    OutlineNode,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    SceneBeat,
    StoryBackground,
    WorldSetting,
    WritingBible,
    WritingMessage,
    WritingRunCommand,
    WritingStyle,
    WritingTask,
)
from ..errors import ApiError
from ..short_story_artifacts import latest_short_story_outline_artifact
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
                    select(WritingTask, Chapter, Novel, WritingBible)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .join(Chapter, Chapter.id == WritingTask.chapterId)
                    .outerjoin(WritingBible, WritingBible.novelId == Novel.id)
                    .where(WritingTask.id == task_id, Novel.userId == user_id)
                )
            ).one_or_none()
            if row is None:
                raise ApiError(
                    status_code=403,
                    code="WRITING_TASK_FORBIDDEN",
                    message="无权访问该写作任务",
                )
            task, chapter, novel, bible = row
            chapter_order = chapter.order
            command = await self._active_command(session, task.id)
            command_payload = _parse_command_payload(command)
            await self._validate_command_identity(
                session,
                task=task,
                chapter=chapter,
                novel=novel,
                bible=bible,
                payload=command_payload,
            )
            goal: ChapterWritingGoal | None = None
            beat_plan: ChapterBeatPlan | None = None
            scenes: list[SceneBeat] = []
            group: ChapterGroupSnapshot | None = None
            outline_path: list[dict[str, Any]] = []
            foreshadowing_summaries: list[dict[str, Any]] = []
            if command_payload.workflowKind == "long_serial":
                groups = await self._chapter_groups(session, task.novelId)
                group = select_unique_chapter_group(chapter_order, groups)
                goal = await session.scalar(
                    select(ChapterWritingGoal)
                    .where(ChapterWritingGoal.chapterId == task.chapterId)
                    .order_by(
                        ChapterWritingGoal.updatedAt.desc(), ChapterWritingGoal.id.desc()
                    )
                    .limit(1)
                )
                beat_plan = await session.scalar(
                    select(ChapterBeatPlan)
                    .where(
                        ChapterBeatPlan.chapterId == task.chapterId,
                        ChapterBeatPlan.status == "approved",
                    )
                    .order_by(
                        ChapterBeatPlan.updatedAt.desc(), ChapterBeatPlan.id.desc()
                    )
                    .limit(1)
                )
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
                outline_path = (
                    await self._outline_path(session, group) if group is not None else []
                )
                foreshadowing_summaries = await self._foreshadowing_summaries(
                    session, task.novelId
                )
            active_artifact = await self._active_artifact(session, task)
            short_story_run_artifact: dict[str, Any] | None = None
            if command_payload.workflowKind == "short_medium":
                latest_user_message = _command_user_message(command_payload)
                recent = await self._recent_messages(
                    session,
                    task.writingSessionId,
                    current_user_message=latest_user_message,
                )
                if command_payload.operation == "write_short_story":
                    short_story_context = await self._short_story_manuscript_context(
                        session,
                        task=task,
                        chapter=chapter,
                        novel=novel,
                        bible=bible,
                        payload=command_payload,
                    )
                    short_story_run_artifact = await self._short_story_run_artifact(
                        session, task
                    )
                    prior_conversation_history = []
                else:
                    current_outline, direct_edit = await self._current_short_outline(
                        session, task.novelId
                    )
                    short_story_context = _build_short_story_context(
                        direct_edit=direct_edit,
                        revision_request=_command_revision_request(command_payload),
                        outline=current_outline,
                        inspiration=(novel.summary or "").strip(),
                        recent_conversation=recent,
                    )
                    prior_conversation_history = recent
            else:
                conversation_history = _conversation_history(task.conversationHistory)
                prior_conversation_history, latest_user_message = (
                    _split_current_user_message(conversation_history)
                )
                short_story_context = None
            return {
                "taskId": task.id,
                "commandId": command.id,
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
                "workflowKind": command_payload.workflowKind,
                "operation": command_payload.operation,
                "targetTotalWordCount": command_payload.targetTotalWordCount,
                "source": (
                    command_payload.source.model_dump(mode="json")
                    if command_payload.source is not None
                    else None
                ),
                "selectedAgents": [item for item in task.selectedAgents.split(",") if item],
                "conversationHistory": prior_conversation_history,
                "userMessage": latest_user_message,
                "shortStoryContext": short_story_context,
                "shortStoryRunArtifact": short_story_run_artifact,
                "graphState": (json.loads(task.graphStateJson) if task.graphStateJson else None),
            }

    async def _short_story_manuscript_context(
        self,
        session: AsyncSession,
        *,
        task: WritingTask,
        chapter: Chapter,
        novel: Novel,
        bible: WritingBible | None,
        payload: WritingJobPayload,
    ) -> dict[str, Any]:
        source = payload.source
        if bible is None or not isinstance(source, ApprovedShortOutlineSource):
            raise _context_identity_mismatch()
        outline_artifact = await session.scalar(
            select(ReviewArtifact).where(ReviewArtifact.id == source.outlineArtifactId)
        )
        if outline_artifact is None:
            raise _context_identity_mismatch()
        outline = _parse_short_outline(outline_artifact.payloadJson)
        background = await session.scalar(
            select(StoryBackground).where(StoryBackground.novelId == task.novelId)
        )
        world_setting = await session.scalar(
            select(WorldSetting).where(WorldSetting.novelId == task.novelId)
        )
        applied_style = None
        if novel.appliedStyleId is not None:
            applied_style = await session.scalar(
                select(WritingStyle).where(
                    WritingStyle.id == novel.appliedStyleId,
                    WritingStyle.userId == novel.userId,
                )
            )
        return {
            "approvedOutline": {
                "artifactId": outline_artifact.id,
                "revision": outline_artifact.revision,
                "hash": canonical_short_outline_hash(outline),
                "payload": outline.model_dump(mode="json"),
            },
            "anchors": outline.anchors.model_dump(mode="json"),
            "originalInspiration": (novel.summary or "").strip(),
            "targetTotalWordCount": bible.targetTotalWordCount,
            "targetChapter": {
                "id": chapter.id,
                "baseContentHash": content_sha256(chapter.content),
            },
            "writingBible": {
                "genre": bible.genre,
                "targetReaders": bible.targetReaders,
                "coreSellingPoint": bible.coreSellingPoint,
                "readerPromise": bible.readerPromise,
                "appealModel": bible.appealModel,
                "taboo": bible.taboo,
                "comparableTitles": bible.comparableTitles,
                "notes": bible.notes,
                "storyLengthProfile": bible.storyLengthProfile,
                "targetTotalWordCount": bible.targetTotalWordCount,
            },
            "storyBackground": (background.content if background is not None else None),
            "worldSetting": (world_setting.content if world_setting is not None else None),
            "appliedStyle": (
                {
                    "id": applied_style.id,
                    "name": applied_style.name,
                    "portraitMarkdown": applied_style.portraitMarkdown,
                    "creativeMethodology": applied_style.creativeMethodology,
                    "expressionFeatures": applied_style.expressionFeatures,
                    "generationStyle": applied_style.generationStyle,
                    "styleTraits": applied_style.styleTraits,
                    "uniqueMarkers": applied_style.uniqueMarkers,
                }
                if applied_style is not None
                else None
            ),
        }

    async def _short_story_run_artifact(
        self,
        session: AsyncSession,
        task: WritingTask,
    ) -> dict[str, Any] | None:
        artifact = await session.scalar(
            select(ReviewArtifact)
            .where(
                ReviewArtifact.taskId == task.id,
                ReviewArtifact.novelId == task.novelId,
                ReviewArtifact.chapterId == task.chapterId,
                ReviewArtifact.kind == "chapter_draft",
            )
            .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
            .limit(1)
        )
        if artifact is None:
            return None
        try:
            draft = ShortStoryChapterDraft.model_validate(json.loads(artifact.payloadJson))
        except (json.JSONDecodeError, ValidationError, TypeError):
            raise _artifact_payload_invalid() from None
        evaluations = list(
            (
                await session.scalars(
                    select(ReviewArtifactEvaluation)
                    .where(
                        ReviewArtifactEvaluation.artifactId == artifact.id,
                        ReviewArtifactEvaluation.revision == artifact.revision,
                    )
                    .order_by(
                        ReviewArtifactEvaluation.createdAt.asc(),
                        ReviewArtifactEvaluation.id.asc(),
                    )
                )
            ).all()
        )
        return {
            "id": artifact.id,
            "taskId": artifact.taskId,
            "artifactKey": artifact.artifactKey,
            "status": artifact.status,
            "revision": artifact.revision,
            "payload": draft.model_dump(mode="json"),
            "evaluations": [
                {
                    "id": item.id,
                    "revision": item.revision,
                    "evaluatorAgent": item.evaluatorAgent,
                    "verdict": item.verdict,
                    "summary": item.summary,
                    "requiredChanges": item.requiredChanges,
                    "createdAt": item.createdAt.isoformat(),
                }
                for item in evaluations
            ],
        }

    async def _active_command(
        self,
        session: AsyncSession,
        task_id: str,
    ) -> WritingRunCommand:
        command = await session.scalar(
            select(WritingRunCommand)
            .where(
                WritingRunCommand.taskId == task_id,
                WritingRunCommand.status.in_(("pending", "submitted", "processing")),
            )
            .order_by(WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc())
            .limit(1)
        )
        if command is None:
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_MISSING",
                message="写作任务缺少当前持久命令",
            )
        return command

    async def _validate_command_identity(
        self,
        session: AsyncSession,
        *,
        task: WritingTask,
        chapter: Chapter,
        novel: Novel,
        bible: WritingBible | None,
        payload: WritingJobPayload,
    ) -> None:
        persisted_profile = bible.storyLengthProfile if bible is not None else "long_serial"
        if (
            payload.chapterId != task.chapterId
            or payload.workflowKind != persisted_profile
        ):
            raise _context_identity_mismatch()
        if persisted_profile == "long_serial":
            return
        target = bible.targetTotalWordCount if bible is not None else None
        if (
            target is None
            or not 6_000 <= target <= 80_000
            or payload.targetTotalWordCount != target
            or task.targetWordCount != target
        ):
            raise _context_identity_mismatch()
        chapter_count = await session.scalar(
            select(func.count(Chapter.id)).where(Chapter.novelId == task.novelId)
        )
        if chapter_count != 1:
            raise _context_identity_mismatch()
        source = payload.source
        if payload.operation == "develop_short_outline":
            if (
                not isinstance(source, ShortOutlineInspirationSource)
                or source.originalInspiration != (novel.summary or "").strip()
            ):
                raise _context_identity_mismatch()
            return
        if not isinstance(source, ApprovedShortOutlineSource):
            raise _context_identity_mismatch()
        artifact = await latest_short_story_outline_artifact(
            session,
            task.novelId,
        )
        if (
            artifact is None
            or artifact.id != source.outlineArtifactId
            or artifact.status != "applied"
            or artifact.revision != source.outlineRevision
        ):
            raise _context_identity_mismatch()
        outline = _parse_short_outline(artifact.payloadJson)
        if _short_outline_hash(outline) != source.outlineHash:
            raise _context_identity_mismatch()

    async def _current_short_outline(
        self,
        session: AsyncSession,
        novel_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        artifact = await latest_short_story_outline_artifact(session, novel_id)
        if artifact is None:
            return None, None
        payload = _parse_short_outline(artifact.payloadJson).model_dump(mode="json")
        try:
            diff = json.loads(artifact.diffJson) if artifact.diffJson is not None else None
        except (json.JSONDecodeError, TypeError):
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_OUTLINE_DIFF_INVALID",
                message="中短篇大纲版本差异记录无效",
            ) from None
        direct_edit = (
            {
                "artifactId": artifact.id,
                "revision": artifact.revision,
                "payload": payload,
                "diff": diff,
            }
            if isinstance(diff, dict) and diff.get("type") == "user_edit"
            else None
        )
        return payload, direct_edit

    async def _recent_messages(
        self,
        session: AsyncSession,
        writing_session_id: str | None,
        *,
        current_user_message: str,
    ) -> list[dict[str, Any]]:
        if writing_session_id is None:
            return []
        records = list(
            (
                await session.scalars(
                    select(WritingMessage)
                    .where(WritingMessage.sessionId == writing_session_id)
                    .order_by(WritingMessage.createdAt.desc(), WritingMessage.id.desc())
                    .limit(7)
                )
            ).all()
        )
        records.reverse()
        recent = [
            {
                "role": record.role,
                "content": record.content,
                "agentId": record.agentId,
            }
            for record in records
        ]
        if (
            recent
            and recent[-1]["role"] == "user"
            and recent[-1]["content"] == current_user_message
        ):
            recent.pop()
        return recent[-6:]

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


def _parse_command_payload(command: WritingRunCommand) -> WritingJobPayload:
    try:
        value = json.loads(command.payloadJson)
    except (json.JSONDecodeError, TypeError):
        raise _context_identity_mismatch() from None
    if not isinstance(value, dict):
        raise _context_identity_mismatch()
    if "workflowKind" not in value:
        value = {
            **value,
            "version": 1,
            "resume": value.get("resume") is True,
            "chapterId": value.get("chapterId"),
            "writingSessionId": value.get("writingSessionId"),
            "resumeInput": value.get("resumeInput"),
            "workflowKind": "long_serial",
            "operation": None,
            "targetTotalWordCount": None,
            "source": None,
        }
    try:
        return WritingJobPayload.model_validate(value)
    except ValidationError:
        raise _context_identity_mismatch() from None


def _command_user_message(payload: WritingJobPayload) -> str:
    for source in (payload.resumeInput, payload.startRequest, payload.decisionRequest):
        if not isinstance(source, dict):
            continue
        value = source.get("userMessage")
        if isinstance(value, str):
            return value
    return ""


def _command_revision_request(payload: WritingJobPayload) -> str | None:
    for source in (payload.resumeInput, payload.decisionRequest):
        if not isinstance(source, dict):
            continue
        value = source.get("userMessage")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _parse_short_outline(serialized: str) -> ShortStoryOutlineDraft:
    try:
        return ShortStoryOutlineDraft.model_validate(json.loads(serialized))
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_OUTLINE_INVALID",
            message="中短篇权威大纲载荷无效",
        ) from None


def _short_outline_hash(outline: ShortStoryOutlineDraft) -> str:
    return canonical_short_outline_hash(outline)


def _context_identity_mismatch() -> ApiError:
    return ApiError(
        status_code=409,
        code="WRITING_CONTEXT_IDENTITY_MISMATCH",
        message="持久命令、作品篇幅或写作来源不一致，不能调用模型",
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


def _build_short_story_context(
    *,
    direct_edit: dict[str, Any] | None,
    revision_request: str | None,
    outline: dict[str, Any] | None,
    inspiration: str,
    recent_conversation: list[dict[str, Any]],
) -> dict[str, Any]:
    """按中短篇权威优先级构造最小上下文，历史只保留最近六条。"""

    anchors = outline.get("anchors") if isinstance(outline, dict) else None
    return {
        "directEdit": direct_edit,
        "revisionRequest": revision_request,
        "anchors": anchors,
        "currentOutline": outline,
        "originalInspiration": inspiration,
        "recentConversation": recent_conversation[-6:],
    }


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
