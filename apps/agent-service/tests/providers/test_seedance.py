"""火山方舟 Seedance 供应商提交边界测试。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from inkforge_agents.providers.seedance import (
    SeedanceProvider,
    SeedanceReference,
)
from inkforge_contracts.video import SeedancePromptPackage
from inkforge_contracts.video_render import (
    SeedanceRenderSubmitRequest,
    SeedanceRuntimeReference,
)
from pydantic import SecretStr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "compile_profile",
    [
        "seedance_director_v3_compat",
        "seedance_cinematic_v2",
        "dual_layer_v1",
        "legacy_single_prompt_v1",
    ],
)
async def test_submit_rejects_compat_and_old_prompt_profiles(
    compile_profile: str,
) -> None:
    """历史兼容包可以读取和预览，但不能越过 1.3 审核门禁真实提交。"""

    provider = _configured_provider()

    with pytest.raises(ValueError, match="SEEDANCE_PROMPT_PROFILE_UNSUPPORTED"):
        await provider.submit(
            _prompt_package(compile_profile=compile_profile),
            [_image_reference()],
        )


@pytest.mark.asyncio
async def test_submit_sends_only_v3_provider_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实请求发送短 Provider 导演稿，完整 Manifest 只留在审核与追溯层。"""

    request_bodies: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "seedance-task-1"})

    def client(_provider: SeedanceProvider) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://ark.example.test/api/v3",
            transport=httpx.MockTransport(handle_request),
        )

    monkeypatch.setattr(SeedanceProvider, "_client", client)
    provider = _configured_provider()
    package = _prompt_package(compile_profile="seedance_director_v3")

    accepted = await provider.submit(package, [_image_reference()])

    assert accepted.taskId == "seedance-task-1"
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["content"][0] == {"type": "text", "text": "供应商短导演稿"}
    assert body["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "https://assets.example.test/reference.png"},
        "role": "reference_image",
    }
    serialized = json.dumps(body, ensure_ascii=False)
    assert "完整制作清单不得发送供应商" not in serialized
    assert "manifestPrompt" not in serialized
    assert "prompt" not in body


@pytest.mark.asyncio
async def test_submit_keeps_preview_gate_ahead_of_profile_gate() -> None:
    """即使提示词版本正确，开发预览包仍必须在接触供应商前被拒绝。"""

    provider = _configured_provider()
    package = _prompt_package(
        compile_profile="seedance_director_v3",
        preview_only=True,
    )

    with pytest.raises(ValueError, match="SEEDANCE_PREVIEW_ONLY"):
        await provider.submit(package, [_image_reference()])


@pytest.mark.asyncio
async def test_submit_render_uses_frozen_prompt_and_runtime_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "provider-task-2"})

    def client(_provider: SeedanceProvider) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://ark.example.test/api/v3",
            transport=httpx.MockTransport(handle_request),
        )

    monkeypatch.setattr(SeedanceProvider, "_client", client)
    response = await _configured_provider().submit_render(
        SeedanceRenderSubmitRequest(
            taskId="render-task-1",
            novelId="novel-1",
            inputHash="a" * 64,
            model="doubao-seedance-2-5-260628",
            promptText="冻结后的逐镜提示词",
            ratio="9:16",
            durationSeconds=5,
            resolution="720p",
            generateAudio=True,
            watermark=False,
            references=[
                SeedanceRuntimeReference(
                    ordinal=1,
                    assetId="asset-1",
                    mimeType="image/png",
                    url="https://media.example.test/reference-token",
                )
            ],
        )
    )

    assert response.providerTaskId == "provider-task-2"
    assert requests == [
        {
            "model": "doubao-seedance-2-5-260628",
            "content": [
                {"type": "text", "text": "冻结后的逐镜提示词"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://media.example.test/reference-token"},
                    "role": "reference_image",
                },
            ],
            "generate_audio": True,
            "ratio": "9:16",
            "duration": 5,
            "resolution": "720p",
            "watermark": False,
        }
    ]


@pytest.mark.asyncio
async def test_query_render_normalizes_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            {
                "status": "succeeded",
                "content": {"video_url": "https://result.volces.com/take.mp4"},
                "duration": "5",
                "resolution": "720p",
                "ratio": "9:16",
                "framespersecond": 24,
                "generate_audio": True,
                "usage": {"total_tokens": 12},
            },
            {
                "status": "failed",
                "error": {"code": "OutputRejected", "message": "结果被拒绝"},
            },
        ]
    )

    async def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    def client(_provider: SeedanceProvider) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://ark.example.test/api/v3",
            transport=httpx.MockTransport(handle_request),
        )

    monkeypatch.setattr(SeedanceProvider, "_client", client)
    provider = _configured_provider()

    succeeded = await provider.query_render(
        task_id="render-task-1",
        provider_task_id="provider-task-1",
    )
    failed = await provider.query_render(
        task_id="render-task-2",
        provider_task_id="provider-task-2",
    )

    assert succeeded.status == "succeeded"
    assert succeeded.output is not None
    assert succeeded.output.videoUrl.endswith("take.mp4")
    assert succeeded.output.durationSeconds == 5
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "OutputRejected"


def _configured_provider() -> SeedanceProvider:
    """构造已开启且带测试密钥的供应商，避免配置门禁掩盖提示词门禁。"""

    return SeedanceProvider(
        api_key=SecretStr("test-api-key"),
        base_url="https://ark.example.test/api/v3",
        enabled=True,
    )


def _image_reference() -> SeedanceReference:
    """构造与单个已物化素材一一对应的图片引用。"""

    return SeedanceReference(
        modality="image",
        url="https://assets.example.test/reference.png",
    )


def _prompt_package(
    *,
    compile_profile: str,
    preview_only: bool = False,
) -> SeedancePromptPackage:
    """构造资产就绪的包；旧单层 profile 按其历史字段形状生成。"""

    provider_prompt = "供应商短导演稿"
    manifest_prompt = "完整制作清单不得发送供应商"
    payload: dict[str, Any] = {
        "sceneId": "scene-provider-test",
        "prompt": provider_prompt,
        "promptCharacterCount": len(provider_prompt),
        "compileProfile": compile_profile,
        "assetBindings": [
            {
                "assetId": "asset01",
                "mediaAssetId": "media-asset-1",
                "alias": "@图片1",
                "modality": "image",
                "duty": "identity",
                "bindingScope": "canon_slot",
                "settingReference": {
                    "kind": "character",
                    "id": "character-1",
                },
                "featureDomain": "character_identity",
                "keyframeRole": None,
                "targetEntity": "人物甲",
                "isFixture": False,
            }
        ],
        "output": {
            "durationSeconds": 5,
            "ratio": "16:9",
        },
        "previewOnly": preview_only,
        "assetReady": True,
        "submissionReady": not preview_only,
        "fixtureOnly": False,
    }
    if compile_profile != "legacy_single_prompt_v1":
        payload.update(
            {
                "providerPrompt": provider_prompt,
                "providerPromptCharacterCount": len(provider_prompt),
                "manifestPrompt": manifest_prompt,
                "manifestPromptCharacterCount": len(manifest_prompt),
            }
        )
    return SeedancePromptPackage.model_validate(payload)
