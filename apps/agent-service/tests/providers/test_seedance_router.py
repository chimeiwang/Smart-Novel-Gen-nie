"""受签名短调用接口保留模拟事实和真实提交未知分类。"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from inkforge_agents.providers.seedance import SeedanceProvider
from inkforge_agents.providers.seedance_router import router
from inkforge_agents.runs.router import get_verifier
from pydantic import SecretStr


class _Verifier:
    async def verify_request(self, **_kwargs: object) -> object:
        return object()


def _body(*, simulated: bool = False) -> dict[str, object]:
    return {
        "taskId": "task-1",
        "novelId": "novel-1",
        "inputHash": "a" * 64,
        "generationMode": "reference",
        "executionMode": "simulated" if simulated else "live",
        "model": "seedance-test",
        "promptText": "正式冻结提示词",
        "ratio": "9:16",
        "durationSeconds": 4,
        "resolution": "720p",
        "generateAudio": True,
        "watermark": False,
        "references": [
            {
                "ordinal": 1,
                "assetId": "asset-1",
                "mimeType": "image/png",
                "url": "https://assets.example/reference.png",
            }
        ],
    }


def _client(provider: SeedanceProvider) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.seedance_provider = provider
    app.dependency_overrides[get_verifier] = _Verifier
    return TestClient(app, headers={"Authorization": "Bearer test-signature"})


@pytest.mark.parametrize(
    ("provider_status", "payload", "expected_status", "expected_code"),
    [
        (408, {}, 502, "SEEDANCE_SUBMISSION_UNKNOWN"),
        (500, {}, 502, "SEEDANCE_SUBMISSION_UNKNOWN"),
        (503, {}, 502, "SEEDANCE_SUBMISSION_UNKNOWN"),
        (200, {}, 502, "SEEDANCE_SUBMISSION_UNKNOWN"),
        (422, {}, 422, "SEEDANCE_SUBMIT_REJECTED"),
    ],
)
def test_submit_router_distinguishes_uncertain_from_rejected(
    monkeypatch: pytest.MonkeyPatch,
    provider_status: int,
    payload: dict[str, Any],
    expected_status: int,
    expected_code: str,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(provider_status, json=payload)

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example", transport=httpx.MockTransport(handler)
        ),
    )
    provider = SeedanceProvider(
        api_key=SecretStr("test-key"),
        base_url="https://ark.example",
        enabled=True,
        execution_mode="live",
    )
    response = _client(provider).post("/internal/v1/video/seedance/tasks", json=_body())

    assert response.status_code == expected_status
    assert expected_code in response.json()["detail"]


def test_submit_and_query_simulation_through_internal_router() -> None:
    client = _client(
        SeedanceProvider(api_key=None, base_url="https://unused.example", enabled=False)
    )
    submitted = client.post("/internal/v1/video/seedance/tasks", json=_body(simulated=True))
    assert submitted.status_code == 202
    assert submitted.json()["providerTaskId"] == "simulated-task-1"

    queried = client.post(
        "/internal/v1/video/seedance/tasks/simulated-task-1/query",
        json={
            "taskId": "task-1",
            "novelId": "novel-1",
            "providerTaskId": "simulated-task-1",
            "executionMode": "simulated",
            "pollCount": 1,
        },
    )
    assert queried.status_code == 200
    assert queried.json()["output"]["videoUrl"] == "inkforge-simulated://task-1"
    assert queried.json()["output"]["lastFrameUrl"] is None
    assert queried.json()["output"]["mediaKind"] == "simulated_placeholder"
    assert queried.json()["output"]["usage"] == {}


def test_query_preserves_last_frame_and_supplier_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def query_live(_provider: SeedanceProvider, _task_id: str) -> dict[str, object]:
        return {
            "status": "succeeded",
            "content": {
                "video_url": "https://result.example/video.mp4",
                "last_frame_url": "https://result.example/last-frame.png",
            },
            "duration": 6.0,
            "resolution": "720p",
            "ratio": "9:16",
            "framespersecond": 24,
            "generate_audio": True,
            "usage": {"completion_tokens": 140, "total_tokens": 140},
        }

    monkeypatch.setattr(SeedanceProvider, "_query_live_task", query_live)
    provider = SeedanceProvider(
        api_key=SecretStr("test-key"),
        base_url="https://ark.example",
        enabled=True,
        execution_mode="live",
    )
    queried = _client(provider).post(
        "/internal/v1/video/seedance/tasks/provider-1/query",
        json={
            "taskId": "task-1",
            "novelId": "novel-1",
            "providerTaskId": "provider-1",
            "executionMode": "live",
            "pollCount": 1,
        },
    )

    assert queried.status_code == 200
    output = queried.json()["output"]
    assert output["lastFrameUrl"] == "https://result.example/last-frame.png"
    assert output["mediaKind"] == "provider_media"
    assert output["usage"] == {"completion_tokens": 140, "total_tokens": 140}
