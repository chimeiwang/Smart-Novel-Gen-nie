"""章节影视化 v2 的共享契约与确定性提示词编译测试。"""

from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts.video_adaptation import (
    BeatCoverageGoal,
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationSourceRange,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    CinematicShotDesignDraft,
    DramaticBeatCandidate,
    SeedanceShotPromptSpec,
    ShotVisualReferenceBundle,
    ShotVisualReferenceSnapshot,
    compile_seedance_shot_prompt,
    parse_video_adaptation_job_payload,
)
from pydantic import ValidationError


def _range(text: str, start: int, end: int) -> ChapterAdaptationSourceRange:
    return ChapterAdaptationSourceRange(
        start=start,
        end=end,
        sourceText=text[start:end],
    )


def _shot(
    *,
    shot_key: str,
    purpose: str,
    source_relation: str,
    source_ranges: list[ChapterAdaptationSourceRange],
    cut_reason: str,
    duration_ms: int = 3000,
) -> CinematicShotCandidate:
    return CinematicShotCandidate.model_validate(
        {
            "shotKey": shot_key,
            "title": f"镜头 {shot_key}",
            "narrativePurpose": purpose,
            "storyFunction": "让观众理解这一镜存在的叙事原因",
            "audienceGain": "观众获得新的动作或情绪信息",
            "coveredGoalKeys": ["G01"],
            "sourceRelation": source_relation,
            "shotScale": "medium",
            "cameraAngle": "eye_level",
            "cameraMovement": "locked",
            "visualIntent": "人物在门口停住并看向桌上的钥匙",
            "speechMode": "none",
            "spokenText": None,
            "soundDesign": "雨声和门轴声",
            "cutReason": cut_reason,
            "timelineDurationMs": duration_ms,
            "sourceRanges": source_ranges,
        }
    )


def test_candidate_supports_scene_beat_and_non_sentence_shot_mapping() -> None:
    source = "“你来了。”林岚抬眼。男人沉默着放下染血的钥匙。"
    dialogue = _range(source, 0, 11)
    reveal = _range(source, 11, len(source))
    candidate = ChapterAdaptationPlanCandidate(
        schemaVersion="chapter_adaptation_plan_v3",
        adaptationId="adaptation-1",
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        scenes=[
            CinematicSceneCandidate(
                sceneKey="SC01",
                title="雨夜书房",
                locationLabel="书房",
                timeLabel="雨夜",
                objective="林岚确认来客带来的线索",
                changeSummary="染血钥匙让等待变成危险预警",
                beats=[
                    DramaticBeatCandidate(
                        beatKey="B01",
                        title="沉默来客交出钥匙",
                        dramaticTurn="林岚从等待转为意识到危险",
                        visualStrategy="让对白跨越空间建立、倾听反应与钥匙揭示",
                        coverageGoals=[
                            BeatCoverageGoal(
                                goalKey="G01",
                                kind="story_information",
                                priority="essential",
                                description="观众确认染血钥匙带来危险线索",
                            )
                        ],
                        sourceRanges=[dialogue, reveal],
                        shots=[
                            _shot(
                                shot_key="S01",
                                purpose="establishing",
                                source_relation="supplemental",
                                source_ranges=[],
                                cut_reason="进入新场景，先建立雨夜书房和人物空间关系",
                                duration_ms=2000,
                            ),
                            _shot(
                                shot_key="S02",
                                purpose="dialogue",
                                source_relation="direct",
                                source_ranges=[dialogue],
                                cut_reason="从空间建立切到林岚发问时的克制表演",
                            ),
                            _shot(
                                shot_key="S03",
                                purpose="reaction",
                                source_relation="supplemental",
                                source_ranges=[],
                                cut_reason="保留来客不回答的倾听反应，延长悬念而非因换人切镜",
                                duration_ms=1500,
                            ),
                            _shot(
                                shot_key="S04",
                                purpose="insert",
                                source_relation="direct",
                                source_ranges=[reveal],
                                cut_reason="关键物件落桌改变信息量，需要插入特写完成揭示",
                                duration_ms=1500,
                            ),
                        ],
                    )
                ],
            )
        ],
        suggestedEpisodeBreakAfterShotKeys=[],
    )

    assert candidate.scenes[0].beats[0].shots[2].sourceRanges == []
    assert candidate.scenes[0].beats[0].shots[3].sourceRanges == [reveal]


@pytest.mark.parametrize("reason", ["说话人变化", "句子结束", "原文换行", "进入下一句"])
def test_candidate_rejects_mechanical_cut_reason(reason: str) -> None:
    with pytest.raises(ValidationError, match="机械切镜理由"):
        _shot(
            shot_key="S01",
            purpose="dialogue",
            source_relation="direct",
            source_ranges=[ChapterAdaptationSourceRange(start=0, end=1, sourceText="甲")],
            cut_reason=reason,
        )


def test_candidate_rejects_non_half_second_duration() -> None:
    with pytest.raises(ValidationError, match="500ms"):
        _shot(
            shot_key="S01",
            purpose="action",
            source_relation="direct",
            source_ranges=[ChapterAdaptationSourceRange(start=0, end=1, sourceText="甲")],
            cut_reason="动作启动后切入主体，明确空间中的行动方向",
            duration_ms=2750,
        )


@pytest.mark.parametrize("duration", [2500.0, "2500", "2.5s"])
def test_formal_candidate_rejects_non_integer_duration(duration: object) -> None:
    with pytest.raises(ValidationError):
        _shot(
            shot_key="S01",
            purpose="action",
            source_relation="direct",
            source_ranges=[ChapterAdaptationSourceRange(start=0, end=1, sourceText="甲")],
            cut_reason="动作方向改变后切入主体近景",
            duration_ms=duration,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("duration", [2500, 2.5, "2.5s", "2500ms"])
def test_model_draft_accepts_common_duration_representations(duration: object) -> None:
    draft = CinematicShotDesignDraft(
        title="推门",
        narrativePurpose="action",
        storyFunction="推进人物进入房间的动作",
        audienceGain="观众确认人物已经进入室内",
        coveredGoalKeys=["G01"],
        sourceRelation="direct",
        shotScale="medium",
        cameraAngle="eye_level",
        cameraMovement="locked",
        visualIntent="人物推门进入房间",
        speechMode="none",
        spokenText=None,
        soundDesign="门轴声",
        cutReason="动作从门外转入门内空间",
        timelineDurationMs=duration,  # type: ignore[arg-type]
        sourceUnitIds=["U001"],
    )

    assert draft.timelineDurationMs == duration


def test_plan_job_payload_verifies_complete_source_hash() -> None:
    source = "甲推门。"
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="雨夜",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )

    assert parse_video_adaptation_job_payload(payload.model_dump(mode="python")) == payload
    with pytest.raises(ValidationError, match="来源哈希"):
        ChapterAdaptationPlanJobPayload.model_validate(
            {**payload.model_dump(mode="python"), "sourceHash": "0" * 64}
        )


def test_visual_reference_snapshot_requires_matching_setting_duty_and_unique_version() -> None:
    reference = ShotVisualReferenceSnapshot(
        canonVersionId="canon-version-1",
        assetId="asset-1",
        assetSha256="a" * 64,
        settingKind="character",
        settingId="character-1",
        settingName="林岚",
        duty="identity",
        variantKey="default",
        label="标准身份",
        includeFeatures=["黑色高马尾"],
        excludeFeatures=["强笑"],
        strength=72,
    )
    bundle = ShotVisualReferenceBundle(shotKey="S01", references=[reference])

    assert bundle.references[0].assetId == "asset-1"
    with pytest.raises(ValidationError, match="职责与文字设定类型不匹配"):
        ShotVisualReferenceSnapshot.model_validate(
            {**reference.model_dump(mode="python"), "settingKind": "location"}
        )
    with pytest.raises(ValidationError, match="不能重复绑定"):
        ShotVisualReferenceBundle(shotKey="S01", references=[reference, reference])


def test_seedance_prompt_compiler_uses_fixed_order_without_truncation() -> None:
    spec = SeedanceShotPromptSpec(
        subjectAndScene="雨夜书房内，林岚坐在桌边，来客停在门口",
        visibleAction="来客将染血钥匙轻放到桌面，林岚的视线随钥匙下落",
        performance="林岚先克制等待，看到血迹后呼吸短暂停顿",
        expressionAndGaze="林岚眉头轻蹙，目光由来客转向钥匙上的血迹",
        camera="中近景固定机位，钥匙落桌时缓慢推近，不越过人物轴线",
        audio="画外持续雨声，钥匙碰桌发出清脆金属声，无新增对白",
        continuity="承接前镜来客站在画面右侧，林岚视线保持向右",
        negativeConstraints=["不要提前展示钥匙来源", "不要新增第三人"],
    )

    prompt = compile_seedance_shot_prompt(
        spec,
        ratio="9:16",
        timeline_duration_ms=3500,
    )

    expected_order = [
        "9:16",
        "3.5 秒",
        spec.subjectAndScene,
        spec.visibleAction,
        spec.performance,
        spec.expressionAndGaze,
        spec.camera,
        spec.audio,
        spec.continuity,
        spec.negativeConstraints[-1],
    ]
    positions = [prompt.index(value) for value in expected_order]
    assert positions == sorted(positions)
    assert "。。" not in prompt
    assert prompt.endswith("不要提前展示钥匙来源；不要新增第三人。")


def test_seedance_prompt_compiler_omits_absent_legacy_sections() -> None:
    spec = SeedanceShotPromptSpec(
        subjectAndScene="黄铜匣嵌在旧钟楼平台中央",
        visibleAction="齿钥转动半圈后骤然卡死",
        expressionAndGaze=None,
        camera="高角度固定近景",
        audio="钥匙卡死时发出短促金属声",
        negativeConstraints=["不得改变第七座灯塔的刮除痕迹"],
    )

    prompt = compile_seedance_shot_prompt(
        spec,
        ratio="16:9",
        timeline_duration_ms=2_000,
    )

    assert "表演：" not in prompt
    assert "表情与视线：" not in prompt
    assert "连续性：" not in prompt
    assert "齿钥转动半圈后骤然卡死" in prompt
