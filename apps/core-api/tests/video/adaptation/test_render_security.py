from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.video.adaptation.render_security import (
    ProviderAssetTokenCodec,
    require_allowed_seedance_result_url,
)


def test_provider_asset_token_is_tamper_evident_and_expires() -> None:
    codec = ProviderAssetTokenCodec("s" * 32, lifetime=timedelta(minutes=5))
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    token = codec.encode(asset_id="asset-1", sha256="a" * 64, now=now)

    grant = codec.decode(token, now=now + timedelta(minutes=1))

    assert grant.asset_id == "asset-1"
    assert grant.sha256 == "a" * 64
    with pytest.raises(ApiError, match="无效或已过期"):
        codec.decode(token + "x", now=now)
    with pytest.raises(ApiError, match="已过期"):
        codec.decode(token, now=now + timedelta(minutes=6))


@pytest.mark.parametrize(
    "url",
    [
        "http://result.volces.com/take.mp4",
        "https://127.0.0.1/take.mp4",
        "https://volces.com/take.mp4",
        "https://volces.com.evil.example/take.mp4",
        "https://user:password@result.volces.com/take.mp4",
    ],
)
def test_seedance_result_url_rejects_non_allowlisted_or_unsafe_hosts(url: str) -> None:
    with pytest.raises(ValueError):
        require_allowed_seedance_result_url(url, (".volces.com",))


def test_seedance_result_url_accepts_allowlisted_https_subdomain() -> None:
    url = "https://ark-output.tos-cn-beijing.volces.com/path/take.mp4?token=1"

    assert require_allowed_seedance_result_url(url, (".volces.com",)) == url
