"""章节影视化公共写入请求的边界测试。"""

from __future__ import annotations

import pytest
from inkforge_core.video.adaptation.schemas import StartPromptRunRequest
from pydantic import ValidationError


def test_prompt_run_rejects_duplicate_shot_targets() -> None:
    with pytest.raises(ValidationError, match="不能重复"):
        StartPromptRunRequest(
            clientRequestId="0123456789abcdef",
            expectedAdaptationRevision=1,
            shotPlanVersionId="plan-1",
            shotIds=["shot-1", "shot-1"],
        )
