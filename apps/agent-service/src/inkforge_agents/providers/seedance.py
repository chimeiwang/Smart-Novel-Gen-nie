"""火山方舟 Seedance 2.5 异步任务适配器。"""

from __future__ import annotations

from typing import Literal, cast

import httpx
from inkforge_contracts.video import SeedancePromptPackage, VideoContractModel
from inkforge_contracts.video_render import (
    SeedanceProviderStatus,
    SeedanceRenderError,
    SeedanceRenderOutput,
    SeedanceRenderQueryResponse,
    SeedanceRenderSubmitRequest,
    SeedanceRenderSubmitResponse,
)
from pydantic import Field, JsonValue, SecretStr


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
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled

    @property
    def configured(self) -> bool:
        """密钥存在只代表已配置，不代表真实渲染已启用。"""

        return self._api_key is not None and bool(self._api_key.get_secret_value())

    async def submit(
        self,
        package: SeedancePromptPackage,
        references: list[SeedanceReference],
    ) -> SeedanceTaskAccepted:
        """提交一次异步任务；fixture 或门禁关闭时确定性拒绝。"""

        # 先校验包的治理级别，避免开发预览因环境开关变化而误入供应商路径。
        if package.previewOnly:
            raise ValueError("SEEDANCE_PREVIEW_ONLY：开发预览包禁止提交供应商")
        if not self._enabled:
            raise RuntimeError("SEEDANCE_DISABLED：真实视频渲染尚未启用")
        if not self.configured or self._api_key is None:
            raise RuntimeError("SEEDANCE_NOT_CONFIGURED：缺少火山方舟 API Key")
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
        async with self._client() as client:
            response = await client.post("/contents/generations/tasks", json=body)
            response.raise_for_status()
            payload = response.json()
        task_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：创建接口缺少任务标识")
        return SeedanceTaskAccepted(taskId=task_id)

    async def query(self, task_id: str) -> SeedanceTaskStatus:
        """查询一次供应商状态，不在请求协程内持续轮询。"""

        if not self._enabled or not self.configured:
            raise RuntimeError("SEEDANCE_DISABLED：真实视频渲染尚未启用")
        async with self._client() as client:
            response = await client.get(f"/contents/generations/tasks/{task_id}")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口返回格式无效")
        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口缺少状态")
        return SeedanceTaskStatus(taskId=task_id, status=status, raw=payload)

    async def submit_render(
        self,
        request: SeedanceRenderSubmitRequest,
    ) -> SeedanceRenderSubmitResponse:
        """提交当前章节改编域的一次冻结逐镜请求，不在 Agent 内重编译输入。"""

        self._require_available()
        content: list[dict[str, object]] = [
            {"type": "text", "text": request.promptText}
        ]
        for reference in sorted(request.references, key=lambda item: item.ordinal):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": reference.url},
                    "role": "reference_image",
                }
            )
        body = {
            "model": request.model,
            "content": content,
            "generate_audio": request.generateAudio,
            "ratio": request.ratio,
            "duration": request.durationSeconds,
            "resolution": request.resolution,
            "watermark": request.watermark,
        }
        async with self._client() as client:
            response = await client.post("/contents/generations/tasks", json=body)
            response.raise_for_status()
            payload = response.json()
        provider_task_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(provider_task_id, str) or not provider_task_id:
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：创建接口缺少任务标识")
        return SeedanceRenderSubmitResponse(
            taskId=request.taskId,
            providerTaskId=provider_task_id,
        )

    async def query_render(
        self,
        *,
        task_id: str,
        provider_task_id: str,
    ) -> SeedanceRenderQueryResponse:
        """查询并规范化一次供应商状态；临时结果 URL 只在成功响应中返回。"""

        self._require_available()
        async with self._client() as client:
            response = await client.get(
                f"/contents/generations/tasks/{provider_task_id}"
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("SEEDANCE_RESPONSE_INVALID：查询接口返回格式无效")
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
        status = cast(SeedanceProviderStatus, raw_status)
        output: SeedanceRenderOutput | None = None
        error: SeedanceRenderError | None = None
        if status == "succeeded":
            content = payload.get("content")
            video_url = content.get("video_url") if isinstance(content, dict) else None
            if not isinstance(video_url, str) or not video_url:
                raise RuntimeError("SEEDANCE_RESPONSE_INVALID：成功任务缺少视频地址")
            output = SeedanceRenderOutput(
                videoUrl=video_url,
                durationSeconds=_optional_float(payload.get("duration")),
                resolution=_optional_text(payload.get("resolution")),
                ratio=_optional_text(payload.get("ratio")),
                framesPerSecond=_optional_int(payload.get("framespersecond")),
                generateAudio=(
                    payload.get("generate_audio")
                    if isinstance(payload.get("generate_audio"), bool)
                    else None
                ),
                usage=_json_object(payload.get("usage")),
            )
        elif status in {"failed", "expired", "cancelled"}:
            raw_error = payload.get("error")
            code = raw_error.get("code") if isinstance(raw_error, dict) else None
            message = raw_error.get("message") if isinstance(raw_error, dict) else None
            error = SeedanceRenderError(
                code=code if isinstance(code, str) and code else f"SEEDANCE_{status.upper()}",
                message=(
                    message
                    if isinstance(message, str) and message
                    else f"Seedance 任务状态为 {status}"
                ),
            )
        return SeedanceRenderQueryResponse(
            taskId=task_id,
            providerTaskId=provider_task_id,
            status=status,
            output=output,
            error=error,
        )

    def _require_available(self) -> None:
        if not self._enabled:
            raise RuntimeError("SEEDANCE_DISABLED：真实视频渲染尚未启用")
        if not self.configured:
            raise RuntimeError("SEEDANCE_NOT_CONFIGURED：缺少火山方舟 API Key")

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
        return parsed if parsed > 0 else None
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
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        return {}
    # 方舟 usage 只应包含 JSON 值；契约校验负责拒绝意外对象。
    return cast(dict[str, JsonValue], value)
