from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from inkforge_core.reviews.repository import _artifact_requires_source_bindings


class Session:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = json.dumps(payload, ensure_ascii=False)

    async def scalar(self, statement: object) -> str:
        del statement
        return self.payload


@pytest.mark.asyncio
async def test_short_medium_outline_artifact_is_not_source_bound() -> None:
    artifact = SimpleNamespace(kind="outline_draft", taskId="task-1")

    assert not await _artifact_requires_source_bindings(
        Session(
            {
                "job": {
                    "workflow": "short_medium",
                    "operation": "generate_outline",
                }
            }
        ),
        artifact,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_long_serial_outline_selection_artifact_is_source_bound() -> None:
    artifact = SimpleNamespace(kind="outline_draft", taskId="task-1")

    assert await _artifact_requires_source_bindings(
        Session(
            {
                "job": {
                    "workflow": "long_serial",
                    "operation": "rewrite_outline_selection",
                }
            }
        ),
        artifact,  # type: ignore[arg-type]
    )
