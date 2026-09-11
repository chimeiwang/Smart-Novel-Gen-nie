"""火山方舟 Seedance 供应商提交边界测试。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from inkforge_agents.providers.seedance import (
    SeedanceProvider,
    SeedanceReference,
    SeedanceSubmissionRejectedError,
    SeedanceSubmissionUnknownError,
)
from inkforge_agents.providers.video_generation import (
    VideoGenerationQuery,
    VideoGenerationReference,
    VideoGenerationRequest,
)
from inkforge_contracts.video import SeedancePromptPackage
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
    response = await _configured_provider().submit_generation(
        VideoGenerationRequest(
            task_id="render-task-1",
            input_hash="a" * 64,
            generation_mode="reference",
            input_profile="image_reference_v1",
            execution_mode="live",
            model="doubao-seedance-2-5-260628",
            prompt_text="冻结后的逐镜提示词",
            ratio="9:16",
            duration_seconds=5,
            resolution="720p",
            output_format="mp4",
            generate_audio=True,
            watermark=False,
            references=[
                VideoGenerationReference(
                    ordinal=1,
                    asset_id="asset-1",
                    modality="image",
                    mime_type="image/png",
                    transport_url="https://media.example.test/reference-token",
                )
            ],
        )
    )

    assert response.provider_task_id == "provider-task-2"
    assert response.simulated is False
    assert requests == [
        {
            "model": "doubao-seedance-2-5-260628",
            "omni_reference_task_type": "reference",
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
            "output_format": "mp4",
            "watermark": False,
        }
    ]


@pytest.mark.asyncio
async def test_submit_generation_maps_documented_multimodal_reference_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_bodies: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "provider-multimodal-1"})

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handle_request)
        ),
    )
    accepted = await _configured_provider().submit_generation(
        VideoGenerationRequest(
            task_id="multimodal-task-1",
            input_hash="b" * 64,
            generation_mode="reference",
            input_profile="multimodal_reference_v1",
            execution_mode="live",
            model="doubao-seedance-2-5-260628",
            prompt_text="使用冻结的图像、动作和音色参考",
            ratio="adaptive",
            duration_seconds=-1,
            resolution="1080p",
            output_format="mov",
            generate_audio=True,
            watermark=False,
            references=[
                VideoGenerationReference(
                    ordinal=1,
                    asset_id="image-1",
                    modality="image",
                    mime_type="image/png",
                    transport_url="asset://image-1",
                ),
                VideoGenerationReference(
                    ordinal=2,
                    asset_id="video-1",
                    modality="video",
                    mime_type="video/mp4",
                    transport_url="https://media.example.test/motion.mp4",
                    usage_role="motion_reference",
                    source_duration_seconds=12,
                ),
                VideoGenerationReference(
                    ordinal=3,
                    asset_id="audio-1",
                    modality="audio",
                    mime_type="audio/mpeg",
                    transport_url="https://media.example.test/voice.mp3",
                    usage_role="voice_reference",
                    source_duration_seconds=8,
                ),
            ],
        )
    )

    assert accepted.provider_task_id == "provider-multimodal-1"
    assert request_bodies[0]["omni_reference_task_type"] == "reference"
    assert request_bodies[0]["duration"] == -1
    assert request_bodies[0]["resolution"] == "1080p"
    assert request_bodies[0]["output_format"] == "mov"
    assert request_bodies[0]["content"][1:] == [
        {
            "type": "image_url",
            "image_url": {"url": "asset://image-1"},
            "role": "reference_image",
        },
        {
            "type": "video_url",
            "video_url": {"url": "https://media.example.test/motion.mp4"},
            "role": "reference_video",
        },
        {
            "type": "audio_url",
            "audio_url": {"url": "https://media.example.test/voice.mp3"},
            "role": "reference_audio",
        },
    ]


@pytest.mark.asyncio
async def test_query_render_normalizes_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            {
                "status": "succeeded",
                "content": {
                    "video_url": "https://result.volces.com/take.mp4",
                    "last_frame_url": "https://result.volces.com/last-frame.png",
                },
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

    succeeded = await provider.query_generation(
        VideoGenerationQuery(
            task_id="render-task-1",
            provider_task_id="provider-task-1",
            execution_mode="live",
        )
    )
    failed = await provider.query_generation(
        VideoGenerationQuery(
            task_id="render-task-2",
            provider_task_id="provider-task-2",
            execution_mode="live",
        )
    )

    assert succeeded.status == "succeeded"
    assert succeeded.output is not None
    assert succeeded.output.video_url.endswith("take.mp4")
    assert succeeded.output.last_frame_url is not None
    assert succeeded.output.last_frame_url.endswith("last-frame.png")
    assert succeeded.output.duration_seconds == 5
    assert succeeded.output.media_kind == "provider_media"
    assert succeeded.output.usage == {"total_tokens": 12}
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "OutputRejected"


def _configured_provider() -> SeedanceProvider:
    """构造已开启且带测试密钥的供应商，避免配置门禁掩盖提示词门禁。"""

    return SeedanceProvider(
        api_key=SecretStr("test-api-key"),
        base_url="https://ark.example.test/api/v3",
        enabled=True,
        execution_mode="live",
    )


def _render_request(*, simulated: bool = False) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        task_id="render-task-1",
        input_hash="a" * 64,
        generation_mode="reference",
        input_profile="image_reference_v1",
        execution_mode="simulated" if simulated else "live",
        model="doubao-seedance-2-5-260628",
        prompt_text="冻结后的逐镜提示词",
        ratio="9:16",
        duration_seconds=5,
        resolution="720p",
        output_format="mp4",
        generate_audio=True,
        watermark=False,
        references=[
            VideoGenerationReference(
                ordinal=1,
                asset_id="asset-1",
                modality="image",
                mime_type="image/png",
                transport_url=(
                    "urn:inkforge:simulated-asset:asset-1"
                    if simulated
                    else "https://media.example.test/reference-token"
                ),
            )
        ],
    )


@pytest.mark.asyncio
async def test_default_simulation_succeeds_without_network_or_in_memory_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_client(_provider: SeedanceProvider) -> httpx.AsyncClient:
        raise AssertionError("模拟路径不得创建网络客户端")

    monkeypatch.setattr(SeedanceProvider, "_client", forbid_client)
    provider = SeedanceProvider(api_key=None, base_url="https://unused.example", enabled=False)
    request = _render_request(simulated=True)
    accepted = await provider.submit_generation(request)
    replayed = await provider.submit_generation(request)
    recreated = SeedanceProvider(api_key=None, base_url="https://unused.example", enabled=False)
    queried = await recreated.query_generation(
        VideoGenerationQuery(
            task_id=request.task_id,
            provider_task_id=accepted.provider_task_id,
            execution_mode="simulated",
        )
    )

    assert accepted == replayed
    assert accepted.provider_task_id == "simulated-render-task-1"
    assert accepted.simulated is True
    assert queried.status == "succeeded"
    assert queried.output is not None
    assert queried.output.video_url == "inkforge-simulated://render-task-1"
    assert queried.output.media_kind == "simulated_placeholder"
    assert queried.output.usage == {}


@pytest.mark.asyncio
async def test_enabled_flag_and_api_key_do_not_override_default_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_client(_provider: SeedanceProvider) -> httpx.AsyncClient:
        raise AssertionError("未显式启用 live 时不得创建网络客户端")

    monkeypatch.setattr(SeedanceProvider, "_client", forbid_client)
    provider = SeedanceProvider(
        api_key=SecretStr("test-key"), base_url="https://unused.example", enabled=True
    )
    with pytest.raises(RuntimeError, match="SEEDANCE_SIMULATED_ONLY"):
        await provider.submit_generation(_render_request())
    with pytest.raises(RuntimeError, match="SEEDANCE_SIMULATED_ONLY"):
        await provider._create_live_task({"model": "test"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "references",
    [
        [
            VideoGenerationReference(
                ordinal=index + 1,
                asset_id=f"video-{index}",
                modality="video",
                mime_type="video/mp4",
                transport_url=f"asset://video-{index}",
                source_duration_seconds=1,
            )
            for index in range(11)
        ],
        [
            VideoGenerationReference(
                ordinal=1,
                asset_id="audio-1",
                modality="audio",
                mime_type="audio/mpeg",
                transport_url="asset://audio-1",
                source_duration_seconds=20,
            ),
            VideoGenerationReference(
                ordinal=2,
                asset_id="audio-2",
                modality="audio",
                mime_type="audio/mpeg",
                transport_url="asset://audio-2",
                source_duration_seconds=11,
            ),
        ],
    ],
)
async def test_seedance_capability_limits_apply_before_simulation(
    references: list[VideoGenerationReference],
) -> None:
    request = _render_request(simulated=True).model_copy(
        update={"input_profile": "multimodal_reference_v1", "references": references}
    )

    with pytest.raises(ValueError, match="SEEDANCE_REFERENCE"):
        await SeedanceProvider(
            api_key=None, base_url="https://unused.example", enabled=False
        ).submit_generation(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_task_id", "execution_mode"),
    [("simulated-another-task", "simulated"), ("simulated-render-task-1", "live")],
)
async def test_simulated_query_rejects_mismatched_task_or_execution_mode(
    provider_task_id: str,
    execution_mode: Any,
) -> None:
    with pytest.raises(ValueError):
        await _configured_provider().query_generation(
            VideoGenerationQuery(
                task_id="render-task-1",
                provider_task_id=provider_task_id,
                execution_mode=execution_mode,
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 500, 502, 503])
async def test_live_submit_uncertain_http_response_is_never_a_definite_rejection(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"error": {"code": "Unknown"}})

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SeedanceSubmissionUnknownError):
        await _configured_provider().submit_generation(_render_request())
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 422, 429])
async def test_live_submit_preserves_explicit_supplier_rejection(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"code": "Rejected"}})

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SeedanceSubmissionRejectedError):
        await _configured_provider().submit_generation(_render_request())


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"{}", b"not-json", b'{"id":" "}', b'{"id":1}'])
async def test_live_submit_missing_identity_stays_unknown(
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SeedanceSubmissionUnknownError):
        await _configured_provider().submit_generation(_render_request())


@pytest.mark.asyncio
async def test_live_submit_timeout_is_unknown_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("受理响应丢失", request=request)

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(SeedanceSubmissionUnknownError):
        await _configured_provider().submit_generation(_render_request())
    assert calls == 1


@pytest.mark.asyncio
async def test_live_query_preserves_complete_supplier_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usage = {"completion_tokens": 80, "total_tokens": 120, "tool_usage": {"web_search": 0}}

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "provider-1",
                "status": "succeeded",
                "content": {"video_url": "https://result.example/take.mp4"},
                "usage": usage,
            },
        )

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    result = await _configured_provider().query_generation(
        VideoGenerationQuery(
            task_id="task-1", provider_task_id="provider-1", execution_mode="live"
        )
    )
    assert result.output is not None
    assert result.output.usage == usage


@pytest.mark.asyncio
async def test_live_query_encodes_provider_task_id_as_one_path_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_paths: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        raw_paths.append(request.url.raw_path)
        return httpx.Response(
            200,
            json={
                "id": "provider/task?part=1",
                "status": "running",
            },
        )

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    result = await _configured_provider().query_generation(
        VideoGenerationQuery(
            task_id="task-1",
            provider_task_id="provider/task?part=1",
            execution_mode="live",
        )
    )

    assert result.status == "running"
    assert raw_paths == [b"/contents/generations/tasks/provider%2Ftask%3Fpart%3D1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("usage", [[], {"total_tokens": -1}, {"total_tokens": True}])
async def test_live_query_never_replaces_invalid_usage_with_zero(
    monkeypatch: pytest.MonkeyPatch,
    usage: object,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "content": {"video_url": "https://result.example/take.mp4"},
                "usage": usage,
            },
        )

    monkeypatch.setattr(
        SeedanceProvider,
        "_client",
        lambda _provider: httpx.AsyncClient(
            base_url="https://ark.example.test", transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(RuntimeError, match="SEEDANCE_USAGE_INVALID"):
        await _configured_provider().query_generation(
            VideoGenerationQuery(
                task_id="task-1", provider_task_id="provider-1", execution_mode="live"
            )
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
