"""章节影视化来源、层级、分集和内容哈希的确定性校验。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

from inkforge_contracts.video_adaptation import ChapterAdaptationPlanCandidate
from pydantic import JsonValue

from ...errors import ApiError


def canonical_json_hash(value: object) -> str:
    """使用稳定 JSON 计算不可变版本内容哈希。"""

    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_plan_against_source(
    plan: ChapterAdaptationPlanCandidate,
    *,
    adaptation_id: str,
    source_text: str,
    source_hash: str,
) -> None:
    """Core 重新切取每个范围，拒绝浏览器或模型伪造来源。"""

    if plan.adaptationId != adaptation_id or plan.sourceHash != source_hash:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_SOURCE_INVALID",
            message="镜头方案与章节改编来源不一致",
        )
    for scene in plan.scenes:
        for beat in scene.beats:
            for source_range in [
                *beat.sourceRanges,
                *(item for shot in beat.shots for item in shot.sourceRanges),
            ]:
                if (
                    source_range.end > len(source_text)
                    or source_text[source_range.start : source_range.end] != source_range.sourceText
                ):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_SOURCE_INVALID",
                        message="镜头方案包含与冻结章节不一致的来源范围",
                    )


def validate_episode_boundaries(
    break_after_shot_ids: Sequence[str],
    *,
    ordered_shot_ids: Sequence[str],
) -> None:
    """分集边界必须唯一、有序且不能落在最后一个镜头之后。"""

    if len(set(break_after_shot_ids)) != len(break_after_shot_ids):
        raise ApiError(
            status_code=409,
            code="VIDEO_EPISODE_BOUNDARY_INVALID",
            message="分集边界不能重复",
        )
    positions = {shot_id: index for index, shot_id in enumerate(ordered_shot_ids)}
    if set(break_after_shot_ids) - set(ordered_shot_ids[:-1]):
        raise ApiError(
            status_code=409,
            code="VIDEO_EPISODE_BOUNDARY_INVALID",
            message="分集边界只能位于当前正式方案的非末尾镜头之后",
        )
    if list(break_after_shot_ids) != sorted(
        break_after_shot_ids,
        key=positions.__getitem__,
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_EPISODE_BOUNDARY_INVALID",
            message="分集边界必须按镜头顺序排列",
        )


def candidate_json(plan: ChapterAdaptationPlanCandidate) -> dict[str, JsonValue]:
    """集中生成可哈希、可落入 ReviewArtifact 的规范候选对象。"""

    return cast(dict[str, JsonValue], plan.model_dump(mode="json"))
