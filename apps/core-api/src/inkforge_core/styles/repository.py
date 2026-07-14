from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..db.base import generate_id
from ..db.models import Novel, StylePortraitTask, StyleReference, WritingStyle
from ..errors import ApiError
from .schemas import PortraitSection
from .service import build_portrait_markdown


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class StyleRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_styles(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            styles = list(
                (
                    await session.scalars(
                        select(WritingStyle)
                        .where(WritingStyle.userId == user_id)
                        .options(
                            selectinload(WritingStyle.references),
                            selectinload(WritingStyle.tasks),
                        )
                        .order_by(WritingStyle.createdAt.desc(), WritingStyle.id.asc())
                    )
                ).all()
            )
        return [self._style_dto(style) for style in styles]

    async def create_style(self, user_id: str, name: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                style = WritingStyle(userId=user_id, name=name, sourceType="agent")
                session.add(style)
                await session.flush()
                await session.refresh(style, attribute_names=["references", "tasks"])
                result = self._style_dto(style)
        return result

    async def reserve_reference(self, user_id: str, style_id: str) -> str:
        async with self._session_factory() as session:
            if (
                await session.scalar(
                    select(WritingStyle.id).where(
                        WritingStyle.id == style_id,
                        WritingStyle.userId == user_id,
                    )
                )
                is None
            ):
                raise self._style_not_found()
        return generate_id()

    async def create_reference(
        self,
        user_id: str,
        style_id: str,
        reference_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                style = await self._lock_owned_style(session, user_id, style_id)
                reference = StyleReference(
                    id=reference_id,
                    styleId=style.id,
                    **fields,
                )
                session.add(reference)
                await session.flush()
                result = self._reference_dto(reference)
        return result

    async def delete_reference(self, user_id: str, style_id: str, reference_id: str) -> str:
        async with self._session_factory() as session:
            async with session.begin():
                await self._lock_owned_style(session, user_id, style_id)
                reference = cast(
                    StyleReference | None,
                    await session.scalar(
                        select(StyleReference)
                        .where(
                            StyleReference.id == reference_id,
                            StyleReference.styleId == style_id,
                        )
                        .with_for_update()
                    ),
                )
                if reference is None:
                    raise ApiError(
                        status_code=404,
                        code="STYLE_REFERENCE_NOT_FOUND",
                        message="文风参考资料不存在",
                    )
                filepath = reference.filepath
                await session.delete(reference)
        return filepath

    async def delete_style(self, user_id: str, style_id: str) -> list[str]:
        async with self._session_factory() as session:
            async with session.begin():
                style = await self._lock_owned_style(session, user_id, style_id)
                paths = list(
                    (
                        await session.scalars(
                            select(StyleReference.filepath)
                            .where(StyleReference.styleId == style_id)
                            .order_by(StyleReference.id.asc())
                        )
                    ).all()
                )
                await session.delete(style)
        return paths

    async def create_portrait_task(
        self,
        user_id: str,
        style_id: str,
        section: PortraitSection | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                style = await self._lock_owned_style(session, user_id, style_id)
                ready_reference = await session.scalar(
                    select(StyleReference.id)
                    .where(
                        StyleReference.styleId == style_id,
                        StyleReference.status == "ready",
                    )
                    .limit(1)
                )
                if ready_reference is None:
                    raise ApiError(
                        status_code=409,
                        code="STYLE_REFERENCE_REQUIRED",
                        message="请先上传可用的文风参考资料",
                    )
                active_task = await session.scalar(
                    select(StylePortraitTask.id)
                    .where(
                        StylePortraitTask.styleId == style_id,
                        StylePortraitTask.status.in_(("pending", "processing")),
                    )
                    .limit(1)
                )
                if active_task is not None:
                    raise ApiError(
                        status_code=409,
                        code="PORTRAIT_TASK_ACTIVE",
                        message="该文风已有画像任务正在执行",
                    )
                task = StylePortraitTask(
                    styleId=style.id,
                    section=section,
                    status="pending",
                    errorMessage=None,
                )
                style.errorMessage = None
                session.add(task)
                await session.flush()
                result = self._task_dto(task)
        return result

    async def get_portrait_sources(
        self, style_id: str, task_id: str
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            task = await session.scalar(
                select(StylePortraitTask).where(
                    StylePortraitTask.id == task_id,
                    StylePortraitTask.styleId == style_id,
                )
            )
            if task is None:
                raise ApiError(
                    status_code=404,
                    code="PORTRAIT_TASK_NOT_FOUND",
                    message="画像任务不存在",
                )
            references = list(
                (
                    await session.scalars(
                        select(StyleReference)
                        .where(
                            StyleReference.styleId == style_id,
                            StyleReference.status == "ready",
                        )
                        .order_by(StyleReference.createdAt, StyleReference.id)
                    )
                ).all()
            )
        return [
            {
                "filepath": reference.filepath,
                "filename": reference.filename,
                "charCount": reference.charCount,
            }
            for reference in references
        ]

    async def get_portrait_task(self, user_id: str, task_id: str) -> dict[str, Any]:
        async with self._session_factory() as session:
            task = await session.scalar(
                select(StylePortraitTask)
                .join(WritingStyle, WritingStyle.id == StylePortraitTask.styleId)
                .where(
                    StylePortraitTask.id == task_id,
                    WritingStyle.userId == user_id,
                )
            )
            if task is None:
                raise self._task_not_found()
            return self._task_dto(task)

    async def transition_portrait_task(
        self,
        style_id: str,
        task_id: str,
        target: str,
        fields: dict[str, Any] | None = None,
        *,
        expected_section: PortraitSection | None = None,
        validate_section: bool = False,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                task = cast(
                    StylePortraitTask | None,
                    await session.scalar(
                        select(StylePortraitTask)
                        .where(StylePortraitTask.id == task_id)
                        .with_for_update()
                    ),
                )
                if task is None:
                    raise self._task_not_found()
                if task.styleId != style_id:
                    raise ApiError(
                        status_code=409,
                        code="PORTRAIT_TASK_MISMATCH",
                        message="画像任务与文风不匹配",
                    )
                if validate_section and task.section != expected_section:
                    raise ApiError(
                        status_code=409,
                        code="PORTRAIT_TASK_SECTION_MISMATCH",
                        message="画像任务分节与完成结果不匹配",
                    )
                style = await self._lock_style(session, style_id)
                if task.status == target and target in {"processing", "success", "error"}:
                    return self._task_dto(task)
                allowed = (task.status, target) in {
                    ("pending", "processing"),
                    ("processing", "success"),
                    ("processing", "error"),
                }
                if not allowed:
                    raise ApiError(
                        status_code=409,
                        code="PORTRAIT_TASK_STATE_CONFLICT",
                        message="画像任务状态冲突",
                    )
                task.status = target
                if target == "success":
                    for name, value in (fields or {}).items():
                        setattr(style, name, value)
                    if expected_section is not None:
                        style.portraitMarkdown = build_portrait_markdown(
                            {
                                "creativeMethodology": style.creativeMethodology,
                                "uniqueMarkers": style.uniqueMarkers,
                                "generationStyle": style.generationStyle,
                                "expressionFeatures": style.expressionFeatures,
                                "styleTraits": style.styleTraits,
                            }
                        )
                    task.errorMessage = None
                    style.errorMessage = None
                elif target == "error":
                    task.errorMessage = "画像生成失败"
                    style.errorMessage = "画像生成失败"
                await session.flush()
                result = self._task_dto(task)
        return result

    async def update_section(
        self,
        user_id: str,
        style_id: str,
        section: PortraitSection,
        content: str,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                style = await self._lock_owned_style(session, user_id, style_id)
                setattr(style, section, content)
                sections = {
                    "creativeMethodology": style.creativeMethodology,
                    "uniqueMarkers": style.uniqueMarkers,
                    "generationStyle": style.generationStyle,
                    "expressionFeatures": style.expressionFeatures,
                    "styleTraits": style.styleTraits,
                }
                style.portraitMarkdown = build_portrait_markdown(sections)
                await session.flush()
                await session.refresh(style, attribute_names=["references", "tasks"])
                result = self._style_dto(style)
        return result

    async def apply_style(
        self,
        novel_id: str,
        user_id: str,
        style_id: str | None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                novel = cast(
                    Novel | None,
                    await session.scalar(
                        select(Novel)
                        .where(Novel.id == novel_id, Novel.userId == user_id)
                        .with_for_update()
                    ),
                )
                if novel is None:
                    raise ApiError(
                        status_code=404,
                        code="NOVEL_NOT_FOUND",
                        message="小说不存在",
                    )
                if style_id is not None:
                    style = await self._lock_owned_style(session, user_id, style_id)
                    if not style.portraitMarkdown:
                        raise ApiError(
                            status_code=409,
                            code="STYLE_PORTRAIT_INCOMPLETE",
                            message="文风画像尚未完整生成",
                        )
                novel.appliedStyleId = style_id

    @staticmethod
    async def _lock_owned_style(
        session: AsyncSession,
        user_id: str,
        style_id: str,
    ) -> WritingStyle:
        style = cast(
            WritingStyle | None,
            await session.scalar(
                select(WritingStyle)
                .where(
                    WritingStyle.id == style_id,
                    WritingStyle.userId == user_id,
                )
                .with_for_update()
            ),
        )
        if style is None:
            raise StyleRepository._style_not_found()
        return style

    @staticmethod
    async def _lock_style(session: AsyncSession, style_id: str) -> WritingStyle:
        style = cast(
            WritingStyle | None,
            await session.scalar(
                select(WritingStyle).where(WritingStyle.id == style_id).with_for_update()
            ),
        )
        if style is None:
            raise StyleRepository._style_not_found()
        return style

    @classmethod
    def _style_dto(cls, style: WritingStyle) -> dict[str, Any]:
        return {
            "id": style.id,
            "name": style.name,
            "sourceType": style.sourceType,
            "creativeMethodology": style.creativeMethodology,
            "uniqueMarkers": style.uniqueMarkers,
            "generationStyle": style.generationStyle,
            "expressionFeatures": style.expressionFeatures,
            "styleTraits": style.styleTraits,
            "portraitMarkdown": style.portraitMarkdown,
            "originalCharCount": style.originalCharCount,
            "usedCharCount": style.usedCharCount,
            "truncated": style.truncated,
            "errorMessage": style.errorMessage,
            "createdAt": _utc(style.createdAt),
            "updatedAt": _utc(style.updatedAt),
            "references": [cls._reference_dto(value) for value in style.references],
            "tasks": [cls._task_dto(value) for value in style.tasks],
        }

    @staticmethod
    def _reference_dto(reference: StyleReference) -> dict[str, Any]:
        return {
            "id": reference.id,
            "styleId": reference.styleId,
            "filename": reference.filename,
            "charCount": reference.charCount,
            "status": reference.status,
            "errorMessage": reference.errorMessage,
            "createdAt": _utc(reference.createdAt),
        }

    @staticmethod
    def _task_dto(task: StylePortraitTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "styleId": task.styleId,
            "section": task.section,
            "status": task.status,
            "errorMessage": task.errorMessage,
            "createdAt": _utc(task.createdAt),
            "updatedAt": _utc(task.updatedAt),
        }

    @staticmethod
    def _style_not_found() -> ApiError:
        return ApiError(status_code=404, code="STYLE_NOT_FOUND", message="文风不存在")

    @staticmethod
    def _task_not_found() -> ApiError:
        return ApiError(
            status_code=404,
            code="PORTRAIT_TASK_NOT_FOUND",
            message="画像任务不存在",
        )
