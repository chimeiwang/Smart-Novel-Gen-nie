"""视觉参考集合必须先落 Head，再写受复合外键约束的子项。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from inkforge_core.db.models import (
    VideoShotVisualReferenceBinding,
    VideoShotVisualReferenceSet,
)
from inkforge_core.video.adaptation.schemas import ShotVisualReferenceSelectionRequest
from inkforge_core.video.adaptation.visual_canon import _replace_shot_reference_bindings


class _RecordingSession:
    def __init__(self) -> None:
        self.events: list[tuple[str, object | None]] = []

    def add(self, value: object) -> None:
        self.events.append(("add", value))

    async def flush(self) -> None:
        self.events.append(("flush", None))

    async def execute(self, statement: object) -> None:
        self.events.append(("execute", statement))


@pytest.mark.asyncio
async def test_new_reference_set_flushes_before_binding_insert() -> None:
    session = _RecordingSession()
    reference_set = VideoShotVisualReferenceSet(
        shotId="shot-1",
        planVersionId="plan-1",
        adaptationId="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        revision=1,
    )

    await _replace_shot_reference_bindings(
        session,  # type: ignore[arg-type]
        reference_set=reference_set,
        reference_set_is_new=True,
        adaptation=SimpleNamespace(
            id="adaptation-1",
            projectId="project-1",
            novelId="novel-1",
        ),  # type: ignore[arg-type]
        shot=SimpleNamespace(id="shot-1", planVersionId="plan-1"),  # type: ignore[arg-type]
        references=[
            ShotVisualReferenceSelectionRequest(
                canonVersionId="canon-version-1",
                strength=76,
            )
        ],
    )

    assert [event for event, _value in session.events] == [
        "add",
        "flush",
        "execute",
        "add",
        "flush",
    ]
    assert session.events[0][1] is reference_set
    binding = session.events[3][1]
    assert isinstance(binding, VideoShotVisualReferenceBinding)
    assert binding.canonVersionId == "canon-version-1"
    assert binding.strength == 76
