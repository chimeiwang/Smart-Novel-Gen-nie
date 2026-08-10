from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import (
    lock_consistency_check,
    replace_chapter_content,
)
from ..db.models import (
    Chapter,
    ChapterBeatPlan,
    ChapterQualityCheck,
    Novel,
    Outline,
    OutlineNode,
    SceneBeat,
)
from ..errors import ApiError
from .apply import ApplicableArtifactPort


class FormalWriteRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def apply_outline(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                await session.execute(
                    pg_insert(Outline)
                    .values(novelId=artifact.novel_id, content=content)
                    .on_conflict_do_update(
                        index_elements=[Outline.novelId], set_={"content": content}
                    )
                )
        return 1

    async def apply_selection(
        self, artifact: ApplicableArtifactPort, user_id: str, replacement: str
    ) -> int:
        payload = artifact.payload
        mode = _selection_mode(payload)
        resource_type, resource_id, start, end, selected_hash, base_hash, base_updated = (
            _selection_identity(payload)
        )
        expected_type = {
            "replace_selection": "chapter_content",
            "outline_content_selection": "outline_content",
            "outline_node_content_selection": "outline_node_content",
        }[mode]
        if resource_type != expected_type:
            raise _selection_conflict(resource_type, resource_id)
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                source: str
                if mode == "replace_selection":
                    if artifact.chapter_id is not None and artifact.chapter_id != resource_id:
                        raise _selection_conflict(resource_type, resource_id)
                    entity = await session.scalar(
                        select(Chapter)
                        .where(
                            Chapter.id == resource_id,
                            Chapter.novelId == artifact.novel_id,
                        )
                        .with_for_update()
                    )
                    if entity is None:
                        raise ApiError(
                            status_code=404,
                            code="CHAPTER_NOT_FOUND",
                            message="姝ｆ枃鑽夋鐩爣绔犺妭涓嶅瓨鍦ㄦ垨涓嶅睘浜庤灏忚",
                        )
                    source = entity.content
                    if not _matches_selection(
                        source,
                        entity.updatedAt,
                        base_updated,
                        base_hash,
                        start,
                        end,
                        selected_hash,
                        selected_text=payload.get("selectedText"),
                        expected_prefix=payload.get("candidatePrefix"),
                        expected_suffix=payload.get("candidateSuffix"),
                    ):
                        raise _selection_conflict(resource_type, resource_id)
                    check = await lock_consistency_check(session, entity.id)
                    if check is None:
                        check = ChapterQualityCheck(
                            chapterId=entity.id,
                            type="consistency",
                            title="涓€鑷存€х粓妫€",
                            status="pending",
                        )
                        session.add(check)
                    await replace_chapter_content(
                        session,
                        entity,
                        check,
                        _splice(source, start, end, replacement),
                        reopen=True,
                    )
                    return 1
                if mode == "outline_content_selection":
                    entity = await session.scalar(
                        select(Outline)
                        .where(
                            Outline.id == resource_id,
                            Outline.novelId == artifact.novel_id,
                        )
                        .with_for_update()
                    )
                    if entity is None:
                        raise ApiError(
                            status_code=404,
                            code="OUTLINE_NOT_FOUND",
                            message="澶х翰涓嶅瓨鍦ㄦ垨涓嶅睘浜庤灏忚",
                        )
                    source = entity.content
                    if not _matches_selection(
                        source,
                        entity.updatedAt,
                        base_updated,
                        base_hash,
                        start,
                        end,
                        selected_hash,
                        selected_text=payload.get("selectedText"),
                        expected_prefix=payload.get("candidatePrefix"),
                        expected_suffix=payload.get("candidateSuffix"),
                    ):
                        raise _selection_conflict(resource_type, resource_id)
                    entity.content = _splice(source, start, end, replacement)
                    return 1
                entity = await session.scalar(
                    select(OutlineNode)
                    .where(
                        OutlineNode.id == resource_id,
                        OutlineNode.novelId == artifact.novel_id,
                    )
                    .with_for_update()
                )
                if entity is None or entity.content is None:
                    raise ApiError(
                        status_code=404,
                        code="OUTLINE_NODE_NOT_FOUND",
                        message="澶х翰鑺傜偣涓嶅瓨鍦ㄦ垨鏃犲唴瀹?",
                    )
                source = entity.content
                if not _matches_selection(
                    source,
                    entity.updatedAt,
                    base_updated,
                    base_hash,
                    start,
                    end,
                    selected_hash,
                    selected_text=payload.get("selectedText"),
                    expected_prefix=payload.get("candidatePrefix"),
                    expected_suffix=payload.get("candidateSuffix"),
                ):
                    raise _selection_conflict(resource_type, resource_id)
                entity.content = _splice(source, start, end, replacement)
        return 1

    async def apply_chapter(
        self, artifact: ApplicableArtifactPort, user_id: str, content: str
    ) -> int:
        payload = artifact.payload
        target = payload.get("target") if payload.get("kind") == "chapter_draft" else None
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                if isinstance(target, dict) and target.get("mode") == "new_next_chapter":
                    maximum = await session.scalar(
                        select(func.max(Chapter.order)).where(Chapter.novelId == artifact.novel_id)
                    )
                    order = (maximum or 0) + 1
                    title = target.get("title")
                    chapter = Chapter(
                        novelId=artifact.novel_id,
                        order=order,
                        title=(title if isinstance(title, str) and title else f"第 {order} 章"),
                        content=content,
                        status="drafting",
                    )
                    session.add(chapter)
                    await session.flush()
                    chapter_id = chapter.id
                else:
                    requested_id = (
                        target.get("chapterId")
                        if isinstance(target, dict) and target.get("mode") == "existing_chapter"
                        else artifact.chapter_id
                    )
                    if not isinstance(requested_id, str) or not requested_id:
                        raise ValueError("正文草案缺少目标章节")
                    existing_chapter = await session.scalar(
                        select(Chapter).where(
                            Chapter.id == requested_id,
                            Chapter.novelId == artifact.novel_id,
                        ).with_for_update()
                    )
                    if existing_chapter is None:
                        raise ApiError(
                            status_code=404,
                            code="CHAPTER_NOT_FOUND",
                            message="正文草案目标章节不存在",
                        )
                    check = await lock_consistency_check(session, existing_chapter.id)
                    if check is None:
                        check = ChapterQualityCheck(
                            chapterId=existing_chapter.id,
                            type="consistency",
                            title="一致性终检",
                            status="pending",
                        )
                        session.add(check)
                    await replace_chapter_content(
                        session,
                        existing_chapter,
                        check,
                        content,
                        reopen=True,
                    )
                    chapter_id = existing_chapter.id
                if not (
                    isinstance(target, dict)
                    and target.get("mode") == "existing_chapter"
                ):
                    await _ensure_consistency_check(session, chapter_id)
        return 1

    async def apply_beat_plan(
        self,
        artifact: ApplicableArtifactPort,
        user_id: str,
        beat_plan: dict[str, object],
    ) -> int:
        if artifact.chapter_id is None:
            raise ValueError("章节计划草案缺少目标章节")
        scenes = beat_plan.get("sceneBeats")
        chapter_goal = beat_plan.get("chapterGoal")
        if not isinstance(chapter_goal, str) or not chapter_goal or not isinstance(scenes, list):
            raise ValueError("章节计划草案结构无效")
        async with self._session_factory() as session:
            async with session.begin():
                await _require_owner(session, artifact.novel_id, user_id)
                chapter = await session.scalar(
                    select(Chapter).where(
                        Chapter.id == artifact.chapter_id,
                        Chapter.novelId == artifact.novel_id,
                    ).with_for_update()
                )
                if chapter is None:
                    raise ApiError(
                        status_code=404,
                        code="CHAPTER_NOT_FOUND",
                        message="章节计划目标章节不存在",
                    )
                await session.execute(
                    update(ChapterBeatPlan)
                    .where(
                        ChapterBeatPlan.chapterId == artifact.chapter_id,
                        ChapterBeatPlan.status == "approved",
                    )
                    .values(status="superseded")
                )
                total = beat_plan.get("totalEstimatedWords")
                plan = ChapterBeatPlan(
                    chapterId=artifact.chapter_id,
                    status="approved",
                    chapterGoal=chapter_goal,
                    mainPlotConnection=_optional_text(beat_plan.get("mainPlotConnection")),
                    chapterAcceptanceCriteria=_optional_text(
                        beat_plan.get("chapterAcceptanceCriteria")
                    ),
                    totalEstimatedWords=(total if isinstance(total, int) else 0),
                )
                session.add(plan)
                await session.flush()
                for index, scene in enumerate(scenes):
                    if not isinstance(scene, dict) or not isinstance(scene.get("goal"), str):
                        raise ValueError("章节计划场景结构无效")
                    characters = scene.get("characters")
                    refs = scene.get("foreshadowingRefs")
                    session.add(
                        SceneBeat(
                            beatPlanId=plan.id,
                            order=(
                                scene["order"] if isinstance(scene.get("order"), int) else index + 1
                            ),
                            goal=scene["goal"],
                            conflict=_optional_text(scene.get("conflict")),
                            characters=json.dumps(
                                characters if isinstance(characters, list) else [],
                                ensure_ascii=False,
                            ),
                            foreshadowingRefs=(
                                json.dumps(refs, ensure_ascii=False)
                                if isinstance(refs, list)
                                else None
                            ),
                            estimatedWords=(
                                scene["estimatedWords"]
                                if isinstance(scene.get("estimatedWords"), int)
                                else 0
                            ),
                            acceptanceCriteria=(
                                scene["acceptanceCriteria"]
                                if isinstance(scene.get("acceptanceCriteria"), str)
                                else scene["goal"]
                            ),
                        )
                    )
        return 1


async def _require_owner(session: AsyncSession, novel_id: str, user_id: str) -> None:
    owner = await session.scalar(select(Novel.userId).where(Novel.id == novel_id).with_for_update())
    if owner != user_id:
        raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")


async def _ensure_consistency_check(session: AsyncSession, chapter_id: str) -> None:
    existing = await session.scalar(
        select(ChapterQualityCheck.id).where(
            ChapterQualityCheck.chapterId == chapter_id,
            ChapterQualityCheck.type == "consistency",
        )
    )
    if existing is None:
        session.add(
            ChapterQualityCheck(
                chapterId=chapter_id,
                type="consistency",
                title="一致性终检",
                status="pending",
            )
        )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _selection_mode(payload: dict[str, object]) -> str:
    target = payload.get("target")
    mode = target.get("mode") if isinstance(target, dict) else None
    if mode not in {
        "replace_selection",
        "outline_content_selection",
        "outline_node_content_selection",
    }:
        raise ValueError("閫夊尯鑽夋缂哄皯鏈夋晥 target mode")
    return cast(str, mode)


def _selection_identity(
    payload: dict[str, object],
) -> tuple[str, str, int, int, str, str, datetime]:
    fields = (
        payload.get("resourceType"),
        payload.get("resourceId"),
        payload.get("selectionStart"),
        payload.get("selectionEnd"),
        payload.get("selectedTextHash"),
        payload.get("baseContentHash"),
        payload.get("baseUpdatedAt"),
    )
    if not isinstance(fields[0], str) or not isinstance(fields[1], str):
        raise ValueError("閫夊尯鑽夋缂哄皯璧勬簮韬唤")
    if (
        isinstance(fields[2], bool)
        or not isinstance(fields[2], int)
        or isinstance(fields[3], bool)
        or not isinstance(fields[3], int)
        or fields[2] < 0
        or fields[3] <= fields[2]
    ):
        raise ValueError("閫夊尯鑽夋鑼冨洿鏃犳晥")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
        for value in (fields[4], fields[5])
    ):
        raise ValueError("閫夊尯鑽夋 hash 鏃犳晥")
    if not isinstance(fields[6], str):
        raise ValueError("閫夊尯鑽夋缂哄皯 baseUpdatedAt")
    try:
        updated = datetime.fromisoformat(fields[6].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("閫夊尯鑽夋 baseUpdatedAt 鏃犳晥") from exc
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return (
        fields[0],
        fields[1],
        fields[2],
        fields[3],
        cast(str, fields[4]),
        cast(str, fields[5]),
        updated,
    )


def _matches_selection(
    source: str,
    updated_at: datetime,
    base_updated_at: datetime,
    base_hash: str,
    start: int,
    end: int,
    selected_hash: str,
    selected_text: object = None,
    expected_prefix: object = None,
    expected_suffix: object = None,
) -> bool:
    current_updated = (
        updated_at.replace(tzinfo=UTC)
        if updated_at.tzinfo is None
        else updated_at.astimezone(UTC)
    )
    selected = source[start:end] if 0 <= start < end <= len(source) else None
    return (
        current_updated == base_updated_at.astimezone(UTC)
        and hashlib.sha256(source.encode("utf-8")).hexdigest() == base_hash
        and selected is not None
        and hashlib.sha256(selected.encode("utf-8")).hexdigest() == selected_hash
        and (selected_text is None or selected_text == selected)
        and (expected_prefix is None or expected_prefix == source[:start])
        and (expected_suffix is None or expected_suffix == source[end:])
    )


def _splice(source: str, start: int, end: int, replacement: str) -> str:
    return source[:start] + replacement + source[end:]


def _selection_conflict(resource_type: str, resource_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="ARTIFACT_SOURCE_VERSION_CONFLICT",
        message="閫夊尯鑽夋鐨勬潵婧愮増鏈凡鍙樺寲",
        details={"resourceType": resource_type, "resourceId": resource_id},
    )
