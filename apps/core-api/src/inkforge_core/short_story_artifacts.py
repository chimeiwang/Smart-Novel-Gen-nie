from __future__ import annotations

import json
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .db.models import (
    Novel,
    Outline,
    ReviewArtifact,
    ReviewArtifactRevision,
    WritingBible,
)
from .errors import ApiError


def writing_bible_lock_statement(
    novel_id: str,
    *,
    user_id: str | None = None,
) -> Select[tuple[WritingBible]]:
    """构造统一的作品圣经行锁，作为中短篇权威来源锁的第一顺序。"""

    statement = select(WritingBible).where(WritingBible.novelId == novel_id)
    if user_id is not None:
        statement = statement.join(Novel, Novel.id == WritingBible.novelId).where(
            Novel.userId == user_id
        )
    return statement.with_for_update(of=WritingBible)


async def lock_writing_bible(
    session: AsyncSession,
    novel_id: str,
    *,
    user_id: str | None = None,
) -> WritingBible | None:
    """锁定作品圣经；所有中短篇大纲写入和整稿应用共用这把行锁。"""

    return cast(
        WritingBible | None,
        await session.scalar(
            writing_bible_lock_statement(novel_id, user_id=user_id)
        ),
    )


async def latest_short_story_outline_artifact(
    session: AsyncSession,
    novel_id: str,
    *,
    for_update: bool = False,
) -> ReviewArtifact | None:
    """选择最新的显式中短篇大纲，跳过未标记的旧流程记录。"""

    statement = (
        select(ReviewArtifact)
        .where(
            ReviewArtifact.novelId == novel_id,
            ReviewArtifact.kind == "outline_draft",
        )
        .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
    )
    if for_update:
        statement = statement.with_for_update()
    candidates = list((await session.scalars(statement)).all())
    for artifact in candidates:
        try:
            payload = json.loads(artifact.payloadJson)
        except (json.JSONDecodeError, TypeError):
            raise ApiError(
                status_code=409,
                code="SHORT_OUTLINE_PAYLOAD_INVALID",
                message="最新中短篇大纲持久化内容不是合法 JSON",
            ) from None
        if (
            isinstance(payload, dict)
            and payload.get("storyLengthProfile") == "short_medium"
        ):
            # 这里只识别显式类型；强类型校验由调用方执行，损坏载荷仍必须报错。
            return artifact
    return None


async def adopted_short_story_outline_revision(
    session: AsyncSession,
    novel_id: str,
    *,
    for_update: bool = False,
) -> tuple[ReviewArtifact, ReviewArtifactRevision] | None:
    """返回当前正式采用的大纲版本，而不是当前最新的待确认草案。

    `ReviewArtifact.status` 只能描述当前草案版本；同一 Artifact 在确认后继续
    修改时会重新进入待确认状态。因此，正式采用版本必须通过 `Outline.content`
    与不可变的修订快照匹配，不能依赖 Artifact 当前状态。
    """

    outline_statement = select(Outline).where(Outline.novelId == novel_id)
    if for_update:
        outline_statement = outline_statement.with_for_update()
    outline = await session.scalar(outline_statement)
    if outline is None:
        # 兼容尚未写入 Outline 正式表的旧项目和历史测试数据。新流程一旦
        # 应用大纲就会写入 Outline，之后始终走下方的不可变修订匹配。
        legacy = await latest_short_story_outline_artifact(
            session,
            novel_id,
            for_update=for_update,
        )
        if legacy is None or legacy.status != "applied":
            return None
        return legacy, ReviewArtifactRevision(
            artifactId=legacy.id,
            revision=legacy.revision,
            payloadJson=legacy.payloadJson,
            diffJson=legacy.diffJson,
            summary=legacy.summary,
            createdByAgent=legacy.updatedByAgent or legacy.createdByAgent,
            createdAt=legacy.updatedAt,
        )

    statement = (
        select(ReviewArtifactRevision, ReviewArtifact)
        .join(
            ReviewArtifact,
            ReviewArtifact.id == ReviewArtifactRevision.artifactId,
        )
        .where(
            ReviewArtifact.novelId == novel_id,
            ReviewArtifact.kind == "outline_draft",
        )
        .order_by(
            ReviewArtifactRevision.createdAt.desc(),
            ReviewArtifactRevision.revision.desc(),
            ReviewArtifactRevision.id.desc(),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    rows = list((await session.execute(statement)).all())
    for revision, artifact in rows:
        try:
            payload = json.loads(revision.payloadJson)
        except (json.JSONDecodeError, TypeError):
            raise ApiError(
                status_code=409,
                code="SHORT_OUTLINE_PAYLOAD_INVALID",
                message="中短篇大纲历史版本不是合法 JSON",
            ) from None
        if (
            isinstance(payload, dict)
            and payload.get("storyLengthProfile") == "short_medium"
            and payload.get("content") == outline.content
        ):
            return cast(ReviewArtifact, artifact), cast(ReviewArtifactRevision, revision)
    return None


async def exact_short_story_outline_revision(
    session: AsyncSession,
    novel_id: str,
    artifact_id: str,
    revision: int,
    *,
    for_update: bool = False,
) -> tuple[ReviewArtifact, ReviewArtifactRevision] | None:
    """读取调用方已经锁定的精确大纲修订，不回退到最新版。"""

    statement = (
        select(ReviewArtifactRevision, ReviewArtifact)
        .join(
            ReviewArtifact,
            ReviewArtifact.id == ReviewArtifactRevision.artifactId,
        )
        .where(
            ReviewArtifact.novelId == novel_id,
            ReviewArtifact.kind == "outline_draft",
            ReviewArtifact.id == artifact_id,
            ReviewArtifactRevision.revision == revision,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).one_or_none()
    if row is not None:
        record, artifact = row
        return cast(ReviewArtifact, artifact), cast(ReviewArtifactRevision, record)

    # 兼容没有 ReviewArtifactRevision 快照的旧 applied 记录。
    artifact_statement = select(ReviewArtifact).where(
        ReviewArtifact.novelId == novel_id,
        ReviewArtifact.kind == "outline_draft",
        ReviewArtifact.id == artifact_id,
        ReviewArtifact.revision == revision,
        ReviewArtifact.status == "applied",
    )
    if for_update:
        artifact_statement = artifact_statement.with_for_update()
    legacy = await session.scalar(artifact_statement)
    if legacy is None:
        return None
    return legacy, ReviewArtifactRevision(
        artifactId=legacy.id,
        revision=legacy.revision,
        payloadJson=legacy.payloadJson,
        diffJson=legacy.diffJson,
        summary=legacy.summary,
        createdByAgent=legacy.updatedByAgent or legacy.createdByAgent,
        createdAt=legacy.updatedAt,
    )
