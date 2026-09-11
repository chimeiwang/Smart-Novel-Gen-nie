"""公共写入口不能把未知状态、局部修订或临时节点当成成功确认。"""

import pytest
from inkforge_core.video.episodes.schemas import (
    StartVideoEpisodeScriptRunRequest,
    VideoEpisodeCommandResponse,
)
from pydantic import ValidationError


def test_revise_cannot_silently_request_a_whole_script():
    with pytest.raises(ValidationError, match="至少一个"):
        StartVideoEpisodeScriptRunRequest(
            clientRequestId="request-123456789",
            expectedDraftRevision=1,
            operation="episode_script_revise",
            instruction="修订这一场",
        )


def test_create_and_reorder_receipts_do_not_require_unknown_episode_identity():
    result = VideoEpisodeCommandResponse(
        clientRequestId="request-123456789",
        episodeId=None,
        operation="reorder",
        resultType="episode_list",
        resultId="project-1",
        resultRevision=2,
        createdAt="2026-09-10T00:00:00Z",
    )
    assert result.resultId == "project-1"
