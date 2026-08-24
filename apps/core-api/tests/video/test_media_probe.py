"""音视频上传时长必须由有限、正值的 ffprobe 结果形成。"""

from __future__ import annotations

import pytest
from inkforge_core.video.media_probe import (
    VideoMediaProbeError,
    _duration_ms_from_probe,
)


def test_duration_probe_rounds_complete_positive_duration() -> None:
    assert _duration_ms_from_probe(b'{"format":{"duration":"1.833333"}}') == 1_833


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b'{"format":{"duration":"N/A"}}',
        b'{"format":{"duration":"0"}}',
        b'{"format":{"duration":"NaN"}}',
    ],
)
def test_duration_probe_rejects_missing_or_nonpositive_duration(payload: bytes) -> None:
    with pytest.raises(VideoMediaProbeError):
        _duration_ms_from_probe(payload)
