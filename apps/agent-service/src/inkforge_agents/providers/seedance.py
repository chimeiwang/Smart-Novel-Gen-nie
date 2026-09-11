"""火山方舟 Seedance 2.5 异步任务适配器。"""

from __future__ import annotations

import json
import math
from typing import Literal, cast
from urllib.parse import quote, urlsplit

import httpx
from inkforge_contracts.video import SeedancePromptPackage, VideoContractModel
from inkforge_contracts.video_render import VideoRenderExecutionMode
from pydantic import Field, JsonValue, SecretStr

from .video_generation import (
    VideoGenerationFailure,
    VideoGenerationIdentity,
    VideoGenerationOutput,
    VideoGenerationQuery,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationStatus,
    VideoGenerationSubmission,
)


class SeedanceSubmissionUnknownError(RuntimeError):
    """请求可能已经创建供应商任务；任何消费者都不得自动再次提交。"""


class SeedanceSubmissionRejectedError(RuntimeError):
    """供应商明确返回创建拒绝，没有可继续查询的已受理任务。"""


class SeedanceReference(VideoContractModel):
    """已通过 Core 归属校验并转换为供应商可读取地址的单个参考素材。"""

    modality: Literal["image", "video", "audio"]
    url: str = Field(min_length=1)


class SeedanceTaskAccepted(VideoContractModel):
    """创建接口返回的稳定任务标识。"""

    taskId: str = Field(min_length=1)


class SeedanceTaskStatus(VideoContractModel):
    """供应商查询结果的最小规范化投影。"""

    taskId: str
    status: str
    raw: dict[str, object]


class SeedanceProvider:
    """只负责短提交和短查询；长轮询由 Core 的耐久任务调度。"""

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        base_url: str,
        enabled: bool,
        execution_mode: VideoRenderExecutionMode = "simulated",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled
        self._execution_mode = execution_mode

    @property
    def configured(self) -> bool:
        """密钥存在只代表已配置，不代表真实渲染已启用。"""

        return self._api_key is not None and bool(self._api_key.get_secret_value())

    @property
    def generation_identity(self) -> VideoGenerationIdentity:
        """声明适配能力；具体模型仍由每个冻结请求决定。"""

        return VideoGenerationIdentity(
            provider="seedance",
            transport_profile="transport.volcengine-ark-video-tasks.v1",
            capability_version="capability.seedance-2.5.reference-multimodal.v1",
            supported_profiles=("image_reference_v1", "multimodal_reference_v1"),
            default_profile="image_reference_v1",
        )

    async def submit(
        self,
        package: SeedancePromptPackage,
        references: list[SeedanceReference],
    ) -> SeedanceTaskAccepted:
        """提交一次异步任务；fixture 或门禁关闭时确定性拒绝。"""

        # 先校验包的治理级别，避免开发预览因环境开关变化而误入供应商路径。
        if package.previewOnly:
            raise ValueError("SEEDANCE_PREVIEW_ONLY：开发预览包禁止提交供应商")
        self._require_live_available()
        if not package.submissionReady or package.fixtureOnly:
            raise ValueError("SEEDANCE_ASSETS_NOT_READY：制作包仍包含占位素材")
        # compat 只用于历史 1.2 场景的可读预览；真实渲染必须来自完整 Scene 1.3 审核包。
        if package.compileProfile != "seedance_director_v3" or package.providerPrompt is None:
            raise ValueError(
                "SEEDANCE_PROMPT_PROFILE_UNSUPPORTED：仅 seedance_director_v3 "
                "提示词可提交，兼容或旧版提示词必须重新规划审核"
            )
        if len(references) != len(package.assetBindings):
            raise ValueError("SEEDANCE_REFERENCE_MISMATCH：素材映射数量不一致")

        # Provider 只接收短提示词；完整制作清单仅用于审核和追溯，不能误发给模型。
        content: list[dict[str, object]] = [{"type": "text", "text": package.providerPrompt}]
        for reference in references:
            # 方舟使用按模态命名的 URL 内容块；局部编号由原始顺序决定。
            content.append(
                {
                    "type": f"{reference.modality}_url",
                    f"{reference.modality}_url": {"url": reference.url},
                    "role": "reference_image" if reference.modality == "image" else "reference",
                }
            )
        body = {
            "model": package.output.model,
            "content": content,
            "generate_audio": package.output.generateAudio,
            "ratio": package.output.ratio,
            "duration": package.output.durationSeconds,
            "resolution": package.output.resolution,
            "output_format": package.output.outputFormat,
            "watermark": package.output.watermark,
        }
        task_id = await self._create_live_task(body)
        return SeedanceTaskAccepted(taskId=task_id)

    async def query(self, task_id: str) -> SeedanceTaskStatus:
        """查询一次供应商状态，不在请求协程内持续轮询。"""

        payload = await self._query_live_task(task_id)
        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口缺少状态")
        return SeedanceTaskStatus(taskId=task_id, status=status, raw=payload)

    async def submit_generation(
        self,
        request: VideoGenerationRequest,
    ) -> VideoGenerationSubmission:
        """把供应商中立的冻结请求翻译成 Seedance wire 请求。"""

        self._validate_reference_capability(request)
        if request.execution_mode == "simulated":
            return VideoGenerationSubmission(
                task_id=request.task_id,
                provider_task_id=f"simulated-{request.task_id}",
                execution_mode="simulated",
                simulated=True,
            )
        self._require_live_available()
        for reference in request.references:
            parsed = urlsplit(reference.transport_url)
            if parsed.scheme not in {"https", "http", "asset"} or not parsed.hostname:
                raise ValueError(
                    "SEEDANCE_REFERENCE_URL_INVALID：真实生成只接受 HTTP(S) 或 asset 参考地址"
                )
        content: list[dict[str, object]] = [{"type": "text", "text": request.prompt_text}]
        for reference in request.references:
            content_type = f"{reference.modality}_url"
            content.append(
                {
                    "type": content_type,
                    content_type: {"url": reference.transport_url},
                    "role": f"reference_{reference.modality}",
                }
            )
        body = {
            "model": request.model,
            "omni_reference_task_type": request.generation_mode,
            "content": content,
            "generate_audio": request.generate_audio,
            "ratio": request.ratio,
            "duration": request.duration_seconds,
            "resolution": request.resolution,
            "output_format": request.output_format,
            "watermark": request.watermark,
        }
        provider_task_id = await self._create_live_task(body)
        return VideoGenerationSubmission(
            task_id=request.task_id,
            provider_task_id=provider_task_id,
            execution_mode="live",
            simulated=False,
        )

    @staticmethod
    def _validate_reference_capability(request: VideoGenerationRequest) -> None:
        """执行 Seedance 2.5 reference 模式的供应商数量和媒体时长上限。"""

        limits = {"image": 30, "video": 10, "audio": 10}
        for modality, limit in limits.items():
            if sum(item.modality == modality for item in request.references) > limit:
                raise ValueError(f"SEEDANCE_REFERENCE_LIMIT：{modality} 参考素材数量超限")
        for modality in ("video", "audio"):
            total_duration = sum(
                item.source_duration_seconds or 0
                for item in request.references
                if item.modality == modality
            )
            if total_duration > 30:
                raise ValueError(f"SEEDANCE_REFERENCE_DURATION_LIMIT：{modality} 总时长超限")

    async def query_generation(self, query: VideoGenerationQuery) -> VideoGenerationResult:
        """查询并规范化一次供应商状态；临时结果 URL 只在成功响应中返回。"""

        if query.execution_mode == "simulated":
            if query.provider_task_id != f"simulated-{query.task_id}":
                raise ValueError("SEEDANCE_SIMULATION_ID_MISMATCH：模拟任务标识与任务不匹配")
            return VideoGenerationResult(
                task_id=query.task_id,
                provider_task_id=query.provider_task_id,
                execution_mode="simulated",
                status="succeeded",
                output=VideoGenerationOutput(
                    video_url=f"inkforge-simulated://{query.task_id}",
                    media_kind="simulated_placeholder",
                ),
            )
        if query.provider_task_id.startswith("simulated-"):
            raise ValueError("SEEDANCE_EXECUTION_MODE_MISMATCH：模拟任务不能查询真实供应商")
        payload = await self._query_live_task(query.provider_task_id)
        raw_status = payload.get("status")
        allowed_statuses = {
            "queued",
            "running",
            "succeeded",
            "failed",
            "expired",
            "cancelled",
        }
        if not isinstance(raw_status, str) or raw_status not in allowed_statuses:
            raise RuntimeError("SEEDANCE_STATUS_UNKNOWN：查询接口返回未知状态")
        status = cast(VideoGenerationStatus, raw_status)
        output: VideoGenerationOutput | None = None
        error: VideoGenerationFailure | None = None
        if status == "succeeded":
            content = payload.get("content")
            video_url = content.get("video_url") if isinstance(content, dict) else None
            if not isinstance(video_url, str) or not video_url:
                raise RuntimeError("SEEDANCE_RESPONSE_INVALID：成功任务缺少视频地址")
            generate_audio = payload.get("generate_audio")
            output = VideoGenerationOutput(
                video_url=video_url,
                last_frame_url=(
                    content.get("last_frame_url")
                    if isinstance(content, dict)
                    and isinstance(content.get("last_frame_url"), str)
                    and content.get("last_frame_url")
                    else None
                ),
                media_kind="provider_media",
                duration_seconds=_optional_float(payload.get("duration")),
                resolution=_optional_text(payload.get("resolution")),
                ratio=_optional_text(payload.get("ratio")),
                frames_per_second=_optional_int(payload.get("framespersecond")),
                generate_audio=generate_audio if isinstance(generate_audio, bool) else None,
                usage=_json_object(payload.get("usage")),
            )
        elif status in {"failed", "expired", "cancelled"}:
            raw_error = payload.get("error")
            code = raw_error.get("code") if isinstance(raw_error, dict) else None
            message = raw_error.get("message") if isinstance(raw_error, dict) else None
            error = VideoGenerationFailure(
                code=code if isinstance(code, str) and code else f"SEEDANCE_{status.upper()}",
                message=(
                    message
                    if isinstance(message, str) and message
                    else f"Seedance 任务状态为 {status}"
                ),
            )
        return VideoGenerationResult(
            task_id=query.task_id,
            provider_task_id=query.provider_task_id,
            execution_mode="live",
            status=status,
            output=output,
            error=error,
        )

    def _require_live_available(self) -> None:
        if self._execution_mode != "live":
            raise RuntimeError("SEEDANCE_SIMULATED_ONLY：当前环境仅允许模拟生成")
        if not self._enabled:
            raise RuntimeError("SEEDANCE_DISABLED：真实视频渲染尚未启用")
        if not self.configured:
            raise RuntimeError("SEEDANCE_NOT_CONFIGURED：缺少火山方舟 API Key")

    async def _create_live_task(self, body: dict[str, object]) -> str:
        """真实付费 POST 的唯一入口；默认模拟，结果不确定时不重发。"""

        self._require_live_available()
        try:
            async with self._client() as client:
                response = await client.post("/contents/generations/tasks", json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500 and exc.response.status_code != 408:
                raise SeedanceSubmissionRejectedError(
                    "SEEDANCE_SUBMIT_REJECTED：Seedance 明确拒绝创建任务"
                ) from exc
            raise SeedanceSubmissionUnknownError(
                "SEEDANCE_SUBMISSION_UNKNOWN：创建请求响应不确定，请勿重复付费提交"
            ) from exc
        except (httpx.RequestError, UnicodeError, ValueError) as exc:
            raise SeedanceSubmissionUnknownError(
                "SEEDANCE_SUBMISSION_UNKNOWN：创建请求未返回有效结果，请勿重复付费提交"
            ) from exc
        provider_task_id = payload.get("id") if isinstance(payload, dict) else None
        if (
            not isinstance(provider_task_id, str)
            or not provider_task_id.strip()
            or provider_task_id != provider_task_id.strip()
        ):
            raise SeedanceSubmissionUnknownError(
                "SEEDANCE_SUBMISSION_UNKNOWN：创建响应缺少有效任务标识，请勿重复付费提交"
            )
        return provider_task_id

    async def _query_live_task(self, provider_task_id: str) -> dict[str, object]:
        """真实 GET 的独立入口；只查询已有任务，不创建或重提任务。"""

        self._require_live_available()
        encoded_task_id = quote(provider_task_id, safe="")
        async with self._client() as client:
            response = await client.get(f"/contents/generations/tasks/{encoded_task_id}")
            response.raise_for_status()
            try:
                payload = response.json()
            except (UnicodeError, ValueError) as exc:
                raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口返回格式无效") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口返回格式无效")
        if payload.get("id", provider_task_id) != provider_task_id:
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询结果与供应商任务不匹配")
        return payload

    def _client(self) -> httpx.AsyncClient:
        """每次短操作使用有界连接，避免把签名或密钥持久化到任务。"""

        if self._api_key is None:
            raise RuntimeError("SEEDANCE_NOT_CONFIGURED：缺少火山方舟 API Key")
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            timeout=httpx.Timeout(30, connect=5),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
        )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) and parsed > 0 else None
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _json_object(value: object) -> dict[str, JsonValue]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError("SEEDANCE_USAGE_INVALID：供应商用量格式无效")
    for key in ("completion_tokens", "total_tokens"):
        count = value.get(key)
        if key in value and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise RuntimeError("SEEDANCE_USAGE_INVALID：供应商用量不是有效非负整数")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("SEEDANCE_USAGE_INVALID：供应商用量不是完整 JSON") from exc
    # 保留所有供应商原始用量字段，不推算费用、不用缺失值伪造零用量。
    return cast(dict[str, JsonValue], value)
