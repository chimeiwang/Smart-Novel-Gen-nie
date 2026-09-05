"""视频阶段的输入、受控诊断与规范化结果不接受隐含接续指令。"""

import hashlib

import pytest
from inkforge_contracts.video_execution import (
    VideoDramaticStructureInput,
    VideoDramaticStructureOutput,
    VideoStageValidationFinding,
    VideoTaskContextV2,
    video_finding_message,
)
from pydantic import ValidationError


def test_video_context_retains_complete_original_payload() -> None:
    source = "正文\n\u001c保留完整来源。"
    value = {
        "taskId": "task-1",
        "payload": {
            "workflow": "chapter_cinematic_adaptation_v2",
            "adaptationId": "adaptation-1",
            "projectId": "project-1",
            "chapterId": "chapter-1",
            "chapterTitle": "原章",
            "sourceText": source,
            "sourceHash": hashlib.sha256(source.encode()).hexdigest(),
            "ratio": "9:16",
            "targetLanguage": "zh-CN",
            "pacingPreset": "short_drama",
            "targetEpisodeSeconds": 60,
        },
        "inheritedCheckpoint": None,
    }
    assert VideoTaskContextV2.model_validate(value).payload.sourceText == source
    with pytest.raises(ValidationError):
        VideoTaskContextV2.model_validate(
            {key: item for key, item in value.items() if key != "inheritedCheckpoint"}
        )


def test_stage_correction_requires_predecessor_and_safe_findings() -> None:
    value = {
        "stageKey": "dramatic_structure",
        "cycle": 0,
        "correction": False,
        "dependencies": [],
        "correctionFindings": [],
    }
    assert not VideoDramaticStructureInput.model_validate(value).correction
    for patch in (
        {"correction": True},
        {"cycle": 1},
        {"nextCall": {}},
        {"cycle": False},
        {"correction": 0},
    ):
        with pytest.raises(ValidationError):
            VideoDramaticStructureInput.model_validate({**value, **patch})


def test_findings_parameters_are_closed_and_do_not_hold_provider_text() -> None:
    value = {
        "code": "prompt_budget",
        "shotKey": "S01",
        "parameters": {"actual": 500, "maximum": 360},
        "blocking": True,
    }
    finding = VideoStageValidationFinding.model_validate(value)
    assert video_finding_message(finding) == "S01 编译后 500 字，超过当前时长的 360 字上限"
    for parameters in (
        {"actual": "供应商原文", "maximum": 360},
        {"raw": "坏参数"},
        {"actual": 500, "maximum": 360, "raw": "坏参数"},
    ):
        with pytest.raises(ValidationError):
            VideoStageValidationFinding.model_validate({**value, "parameters": parameters})


def test_dramatic_outcome_cannot_smuggle_partial_checkpoint_as_ready() -> None:
    with pytest.raises(ValidationError):
        VideoDramaticStructureOutput.model_validate(
            {
                "stageKey": "dramatic_structure",
                "outcome": "ready",
                "validationFindings": [],
                "checkpoint": None,
            }
        )
