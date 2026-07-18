from __future__ import annotations

import json
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .db.models import Novel, ReviewArtifact, WritingBible
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
