"""章节影视化读模型的候选与正式版本消歧测试。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from inkforge_contracts.video_adaptation import (
    SeedanceShotPromptSpec,
    ShotPromptSpecBatch,
    ShotPromptSpecCandidate,
    compile_seedance_shot_prompt,
)
from inkforge_core.video.adaptation.read_model import _prompt_candidates_from_tasks
from inkforge_core.video.adaptation.schemas import ShotPromptVersionResponse


def _prompt_spec() -> SeedanceShotPromptSpec:
    return SeedanceShotPromptSpec(
        subjectAndScene="雾港钟楼外，林岚站在雨中",
        visibleAction="林岚抬头看向钟楼顶端",
        performance="神情戒备，呼吸克制",
        camera="中景缓慢推近至近景",
        audio="海风、雨声与远处钟声",
        continuity="人物面向画面右侧",
        negativeConstraints=["禁止字幕", "禁止多余人物"],
    )


def _task(
    spec: SeedanceShotPromptSpec,
    *,
    task_id: str = "task-1",
    shot_key: str = "S01",
) -> SimpleNamespace:
    batch = ShotPromptSpecBatch(
        prompts=[ShotPromptSpecCandidate(shotKey=shot_key, spec=spec)]
    )
    return SimpleNamespace(
        id=task_id,
        kind="shot_prompt",
        status="completed",
        baseShotPlanVersionId="plan-1",
        resultJson=json.dumps(
            {"promptBatch": batch.model_dump(mode="json")},
            ensure_ascii=False,
        ),
    )


def _plan() -> SimpleNamespace:
    shots = [
        SimpleNamespace(id="shot-1", shotKey="S01", timelineDurationMs=2_500),
        SimpleNamespace(id="shot-2", shotKey="S02", timelineDurationMs=3_000),
    ]
    beat = SimpleNamespace(shots=shots)
    scene = SimpleNamespace(beats=[beat])
    return SimpleNamespace(planVersionId="plan-1", scenes=[scene])


def test_prompt_candidate_remains_visible_before_it_is_saved() -> None:
    candidates = _prompt_candidates_from_tasks(  # type: ignore[arg-type]
        [_task(_prompt_spec())],
        current_plan=_plan(),
        prompt_versions=[],
        ratio="16:9",
    )

    assert len(candidates) == 1
    assert candidates[0].shotId == "shot-1"


def test_saved_prompt_candidate_does_not_override_manual_current_text() -> None:
    spec = _prompt_spec()
    generated = compile_seedance_shot_prompt(
        spec,
        ratio="16:9",
        timeline_duration_ms=2_500,
    )
    saved = ShotPromptVersionResponse(
        id="prompt-version-1",
        shotId="shot-1",
        shotKey="S01",
        versionNo=1,
        generatedText=generated,
        currentText=f"{generated} 手动补充连续性。",
        promptEdited=True,
        headRevision=2,
        createdAt=datetime(2026, 8, 18, tzinfo=UTC),
    )

    candidates = _prompt_candidates_from_tasks(  # type: ignore[arg-type]
        [_task(spec)],
        current_plan=_plan(),
        prompt_versions=[saved],
        ratio="16:9",
    )

    assert candidates == []


def test_new_single_shot_task_keeps_other_unsaved_candidates_visible() -> None:
    first_spec = _prompt_spec()
    second_spec = first_spec.model_copy(
        update={"visibleAction": "林岚从邮袋中抽出灰蓝色信封"}
    )

    candidates = _prompt_candidates_from_tasks(  # type: ignore[arg-type]
        [
            _task(second_spec, task_id="task-new", shot_key="S02"),
            _task(first_spec, task_id="task-old", shot_key="S01"),
        ],
        current_plan=_plan(),
        prompt_versions=[],
        ratio="16:9",
    )

    assert [(item.shotKey, item.taskId) for item in candidates] == [
        ("S01", "task-old"),
        ("S02", "task-new"),
    ]
