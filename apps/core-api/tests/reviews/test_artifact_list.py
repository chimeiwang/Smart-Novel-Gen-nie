from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.repository import _decode_cursor, _encode_cursor


def test_artifact_cursor_round_trips_created_at_and_identifier() -> None:
    artifact = SimpleNamespace(
        id="artifact-2",
        createdAt=datetime(2026, 8, 6, 12, 30, tzinfo=UTC),
    )

    created_at, artifact_id = _decode_cursor(_encode_cursor(artifact))

    assert created_at == artifact.createdAt
    assert artifact_id == artifact.id


def test_artifact_cursor_rejects_invalid_value() -> None:
    with pytest.raises(ApiError) as caught:
        _decode_cursor("not-a-cursor")

    assert caught.value.status_code == 422
    assert caught.value.code == "REVIEW_ARTIFACT_CURSOR_INVALID"
