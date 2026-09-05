"""仅供视频 V2 单 Step 的官方 Responses 适配；不改变旧聊天或 V1 Provider。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ..config import Settings
from .base import (
    ModelFinishReason,
    ModelMessage,
    ModelStructuredOutputDiagnostic,
    ModelStructuredOutputDiagnosticCode,
    ModelStructuredOutputRequest,
    ModelTurnRequest,
    ProviderProtocolError,
    ProviderTransportError,
)
from .openai_compatible import (
    StructuredOutputRecoveryCode,
    _compile_responses_wire_schema,
    _compile_structured_output_schema,
    _is_official_deepseek_endpoint,
    _parse_and_validate_structured_output,
    _reject_duplicate_json_keys,
    _reject_nonstandard_json_constant,
    _schema_sha256,
)

_ENDPOINT = "https://api.deepseek.com/responses"
_MODEL = "deepseek-v4-flash"
_Counter = Annotated[int, Field(ge=0, strict=True)]


@dataclass(frozen=True, slots=True)
class VideoResponsesIdentity:
    provider: str = "openai_compatible"
    model: str = _MODEL
    transport_profile: str = "transport.deepseek-responses.v1"
    endpoint_profile: str = "endpoint.deepseek-responses-official.v1"
    capability_version: str = "capability.deepseek-responses.json-schema.v1"
    supports_request_idempotency: bool = False


class VideoResponsesRequest(BaseModel):
    """无工具、关闭思考的阶段输入；局部 Schema 不代替供应商 wire 投影。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    messages: list[ModelMessage] = Field(min_length=1)
    maxOutputTokens: Annotated[int, Field(gt=0, strict=True)]
    structuredOutput: ModelStructuredOutputRequest

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.structuredOutput.route != "responses_json_schema_v1" or any(
            message.role == "tool"
            or message.tool_calls
            or message.tool_call_id is not None
            or message.reasoningContent is not None
            for message in self.messages
        ):
            raise ValueError("视频 Responses 只能使用无工具历史的原结构化文本路由")
        _compile_structured_output_schema(self.structuredOutput)
        _compile_responses_wire_schema(self.structuredOutput)
        return self

    @classmethod
    def from_turn(cls, turn: ModelTurnRequest) -> Self:
        if (
            turn.tools
            or turn.requiredToolName is not None
            or turn.policy.requiredToolName is not None
            or turn.policy.thinkingMode != "disabled"
            or turn.thinkingMode != "disabled"
            or turn.requestIdempotencyKey is not None
            or turn.structuredOutput is None
        ):
            raise ValueError("视频 Responses 必须关闭思考和工具，不声明供应商请求幂等")
        return cls(
            messages=[message.model_copy(deep=True) for message in turn.messages],
            maxOutputTokens=turn.maxOutputTokens,
            structuredOutput=turn.structuredOutput.model_copy(deep=True),
        )


class VideoResponsesUsage(BaseModel):
    """只保存可靠事实；成本没有已声明单位，不从 token 或任意供应商字段推算。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    inputTokens: _Counter | None = None
    cachedTokens: _Counter | None = None
    promptCacheMissTokens: _Counter | None = None
    completionTokens: _Counter | None = None
    reasoningTokens: _Counter | None = None
    visibleOutputTokens: _Counter | None = None
    totalTokens: _Counter | None = None
    costMicros: _Counter | None = None

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        if self.inputTokens is not None and self.cachedTokens is not None:
            if self.cachedTokens > self.inputTokens:
                raise ValueError("缓存 token 不能超过输入")
            if (
                self.promptCacheMissTokens is not None
                and self.cachedTokens + self.promptCacheMissTokens != self.inputTokens
            ):
                raise ValueError("缓存与未命中 token 必须闭合")
        if self.completionTokens is not None and self.reasoningTokens is not None:
            if self.reasoningTokens > self.completionTokens:
                raise ValueError("推理 token 不能超过输出")
            if (
                self.visibleOutputTokens is not None
                and self.reasoningTokens + self.visibleOutputTokens != self.completionTokens
            ):
                raise ValueError("推理与可见输出 token 必须闭合")
        if (
            self.totalTokens is not None
            and self.inputTokens is not None
            and self.completionTokens is not None
        ):
            if self.totalTokens != self.inputTokens + self.completionTokens:
                raise ValueError("总 token 与输入输出必须闭合")
        return self


@dataclass(frozen=True, slots=True)
class VideoResponsesResult:
    structuredOutput: dict[str, JsonValue] | None
    diagnostic: ModelStructuredOutputDiagnostic | None
    finishReason: ModelFinishReason
    rawFinishReason: str
    providerResponseId: str | None
    usage: VideoResponsesUsage
    localSchemaSha256: str
    wireSchemaSha256: str
    recoveryCode: StructuredOutputRecoveryCode | None = None


class ExecutionResponsesProvider(Protocol):
    @property
    def identity(self) -> VideoResponsesIdentity: ...

    async def complete_responses(self, request: VideoResponsesRequest) -> VideoResponsesResult: ...


class ResponsesExecutionPort(Protocol):
    @property
    def responses_identity(self) -> VideoResponsesIdentity | None: ...

    async def run_execution_responses(
        self,
        request: VideoResponsesRequest,
        *,
        before_provider: Callable[[], Awaitable[int]],
        lane: Literal["interactive", "creative", "batch_media"],
        provider_timeout_seconds: float | None = None,
    ) -> tuple[int, VideoResponsesResult]: ...


class DeepSeekVideoResponsesProvider:
    def __init__(self, settings: Settings, *, http: httpx.AsyncClient | None = None) -> None:
        if (
            settings.openai_model != _MODEL
            or not _is_official_deepseek_endpoint(settings.openai_base_url)
            or settings.openai_api_key is None
            or not settings.openai_api_key.get_secret_value()
        ):
            raise ValueError("视频 V2 Responses 只支持已配置密钥的官方 deepseek-v4-flash")
        self.identity = VideoResponsesIdentity()
        self._authorization = "Bearer " + settings.openai_api_key.get_secret_value()
        self._owns_http = http is None
        # HTTPX 默认 transport 无重试；不使用 SDK、代理环境或重定向回退。
        self._http = (
            http
            if http is not None
            else httpx.AsyncClient(
                # 原 Responses SDK 默认 600 秒；真正单 Step 墙钟由共用 Runtime 的冻结预算限制。
                timeout=600.0,
                trust_env=False,
                follow_redirects=False,
            )
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def complete_responses(self, request: VideoResponsesRequest) -> VideoResponsesResult:
        validator = _compile_structured_output_schema(request.structuredOutput)
        wire_schema = _compile_responses_wire_schema(request.structuredOutput)
        body = {
            "model": self.identity.model,
            "input": [
                {"type": "message", "role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_output_tokens": request.maxOutputTokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.structuredOutput.name,
                    "schema": wire_schema,
                }
            },
            "reasoning": {"effort": "none"},
        }
        response = None
        transport_error = None
        try:
            response = await self._http.post(
                _ENDPOINT,
                json=body,
                headers={"Authorization": self._authorization},
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            transport_error = ProviderTransportError(
                code="timeout_error", statusCode=None, requestId=None
            )
        except httpx.HTTPError:
            transport_error = ProviderTransportError(
                code="connection_error", statusCode=None, requestId=None
            )
        # 离开 except 后再抛出，不挂载包含 URL、正文或密钥的底层异常上下文。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("视频 Responses 未返回响应")
        if not response.is_success:
            raise ProviderTransportError(
                code="http_error", statusCode=response.status_code, requestId=None
            )
        invalid_json = False
        try:
            payload = json.loads(
                response.content,
                parse_constant=_reject_nonstandard_json_constant,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (ValueError, UnicodeError):
            invalid_json = True
            payload = None
        if invalid_json:
            raise ProviderProtocolError(
                code="invalid_response_json", statusCode=response.status_code, requestId=None
            )
        envelope = payload if isinstance(payload, dict) else {}
        usage = _usage(envelope)
        response_id = envelope.get("id")
        provider_response_id = response_id if isinstance(response_id, str) and response_id else None
        local_schema_hash = _schema_sha256(request.structuredOutput.jsonSchema)
        wire_schema_hash = _schema_sha256(wire_schema)

        def failure(
            code: ModelStructuredOutputDiagnosticCode,
            keyword: str,
            finish: ModelFinishReason = "unknown",
            raw: str = "response.completed",
        ) -> VideoResponsesResult:
            return VideoResponsesResult(
                structuredOutput=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code=code, jsonPointer="", keyword=keyword
                ),
                finishReason=finish,
                rawFinishReason=raw,
                providerResponseId=provider_response_id,
                usage=usage,
                localSchemaSha256=local_schema_hash,
                wireSchemaSha256=wire_schema_hash,
            )

        status = envelope.get("status")
        if status == "incomplete":
            details = envelope.get("incomplete_details")
            reason = details.get("reason") if isinstance(details, dict) else None
            finish: ModelFinishReason = (
                "length"
                if reason == "max_output_tokens"
                else "content_filter"
                if reason == "content_filter"
                else "unknown"
            )
            raw = (
                f"response.incomplete:{reason}"
                if reason in ("max_output_tokens", "content_filter")
                else "response.incomplete"
            )
            return failure("response_incomplete", "status", finish, raw)
        if status == "failed":
            return failure("response_failed", "status", raw="response.failed")
        if status != "completed":
            return failure("unexpected_output", "status", raw="response.unknown_status")
        output = envelope.get("output")
        if not isinstance(output, list):
            return failure("unexpected_output", "output")
        texts = []
        for item in output:
            if not isinstance(item, dict):
                return failure("unexpected_output", "output")
            if item.get("type") == "reasoning":
                continue
            if item.get("type") != "message":
                return failure("unexpected_output", "output")
            if item.get("status") in ("in_progress", "incomplete"):
                return failure(
                    "response_incomplete", "status", raw="response.completed:item_incomplete"
                )
            content = item.get("content")
            if not isinstance(content, list):
                return failure("unexpected_output", "output")
            for block in content:
                if (
                    not isinstance(block, dict)
                    or block.get("type") != "output_text"
                    or not isinstance(block.get("text"), str)
                ):
                    return failure("unexpected_output", "output")
                texts.append(block["text"])
        if len(texts) > 1:
            return failure("multiple_text_outputs", "content", "stop")
        parsed, diagnostic, recovery = _parse_and_validate_structured_output(
            raw_text=texts[0] if texts else "",
            structured_output=request.structuredOutput,
            validator=validator,
        )
        return VideoResponsesResult(
            structuredOutput=cast(dict[str, JsonValue] | None, parsed),
            diagnostic=diagnostic,
            finishReason="stop",
            rawFinishReason="response.completed",
            recoveryCode=recovery,
            providerResponseId=provider_response_id,
            usage=usage,
            localSchemaSha256=local_schema_hash,
            wireSchemaSha256=wire_schema_hash,
        )


def _counter(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _details(usage: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = usage.get(key)
    return value if isinstance(value, dict) else {}


def _usage(payload: Mapping[str, object]) -> VideoResponsesUsage:
    value = payload.get("usage")
    if not isinstance(value, dict):
        return VideoResponsesUsage()
    input_tokens = _counter(value.get("input_tokens"))
    completion = _counter(value.get("output_tokens"))
    total = _counter(value.get("total_tokens"))
    if "total_tokens" in value and (
        total is None
        or (
            input_tokens is not None
            and completion is not None
            and total != input_tokens + completion
        )
    ):
        return VideoResponsesUsage()
    details = _details(value, "input_tokens_details")
    cache_values = [details[key] for key in ("cached_tokens", "cache_read") if key in details]
    if "prompt_cache_hit_tokens" in value:
        cache_values.append(value["prompt_cache_hit_tokens"])
    cached = None
    if (
        cache_values
        and all(_counter(item) is not None for item in cache_values)
        and len(set(cache_values)) == 1
    ):
        cached = _counter(cache_values[0])
    miss = None
    if input_tokens is not None and cached is not None:
        if cached > input_tokens:
            cached = None
        else:
            miss = input_tokens - cached
    reasoning = _counter(_details(value, "output_tokens_details").get("reasoning_tokens"))
    visible = None
    if completion is not None and reasoning is not None:
        if reasoning > completion:
            reasoning = None
        else:
            visible = completion - reasoning
    return VideoResponsesUsage(
        inputTokens=input_tokens,
        cachedTokens=cached,
        promptCacheMissTokens=miss,
        completionTokens=completion,
        reasoningTokens=reasoning,
        visibleOutputTokens=visible,
        totalTokens=total,
    )
