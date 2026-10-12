"""V2 独立 embedding 单 HTTP 适配，不改变旧 embed/query 客户端。"""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import httpx
from inkforge_contracts.rag_execution import RagEmbeddingBatchOutput
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .base import ProviderProtocolError, ProviderTransportError
from .error_details import (
    capture_failure_diagnostic,
    capture_provider_error_details,
    log_failure_diagnostic,
)

logger = logging.getLogger(__name__)


def embedding_endpoint(base_url: str) -> str:
    """沿原客户端规则得到请求端点配置字符串，不做 URL 或正文规范化。"""
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/embeddings"


def embedding_endpoint_profile(base_url: str) -> str:
    digest = hashlib.sha256(embedding_endpoint(base_url).encode("utf-8")).hexdigest()
    return f"endpoint.rag-embedding.{digest}.v1"


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    model: str
    endpoint_profile: str
    provider: str = "openai_embeddings"
    transport_profile: str = "transport.openai-embeddings.v1"
    capability_version: str = "capability.openai-embeddings.batch.v1"


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    texts: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1, max_length=10)]


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    embeddings: list[list[float]] | None
    input_tokens: int | None
    protocol_error: Literal["EMBEDDING_OUTPUT_INVALID"] | None = None


class ExecutionEmbeddingProvider(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    async def embed_batch(self, request: EmbeddingRequest) -> EmbeddingResult: ...


class EmbeddingExecutionPort(Protocol):
    @property
    def embedding_identity(self) -> EmbeddingIdentity | None: ...

    async def run_execution_embedding(
        self,
        request: EmbeddingRequest,
        *,
        before_provider: Callable[[], Awaitable[int]],
        lane: Literal["interactive", "creative", "batch_media"],
        provider_timeout_seconds: float | None = None,
    ) -> tuple[int, EmbeddingResult]: ...


class OpenAIExecutionEmbeddingProvider:
    def __init__(self, http: httpx.AsyncClient, *, model: str, base_url: str) -> None:
        if not model or not base_url:
            raise ValueError("索引模型与端点配置不能为空")
        self._http = http
        self._endpoint = embedding_endpoint(base_url)
        self.identity = EmbeddingIdentity(
            model=model, endpoint_profile=embedding_endpoint_profile(base_url)
        )

    def _error_secrets(self) -> tuple[str, ...]:
        values = []
        for header in ("authorization", "x-api-key", "api-key", "cookie"):
            value = self._http.headers.get(header, "")
            if value:
                values.append(value)
                if header == "authorization" and " " in value:
                    values.append(value.split(" ", 1)[1])
        return tuple(values)

    def _log_provider_error(self, error: ProviderTransportError | ProviderProtocolError) -> None:
        """独立 HTTP 路由记录完整失败详情，不依赖业务终态结果带回诊断。"""
        log_failure_diagnostic(
            logger,
            capture_failure_diagnostic(
                stage="transport" if isinstance(error, ProviderTransportError) else "response_json",
                code=error.code,
                details=error.details,
                secrets=self._error_secrets(),
            ),
            provider=self.identity.provider,
            model=self.identity.model,
        )

    def _log_failure(self, stage: str, payload: object, error: Exception | None = None) -> None:
        log_failure_diagnostic(
            logger,
            capture_failure_diagnostic(
                stage=stage,
                code="EMBEDDING_OUTPUT_INVALID",
                payload=payload,
                error=error,
                secrets=self._error_secrets(),
            ),
            provider=self.identity.provider,
            model=self.identity.model,
        )

    async def embed_batch(self, request: EmbeddingRequest) -> EmbeddingResult:
        response: httpx.Response | None = None
        error: ProviderTransportError | None = None
        try:
            response = await self._http.post(
                self._endpoint, json={"model": self.identity.model, "input": request.texts}
            )
        except httpx.TimeoutException as exc:
            error = ProviderTransportError(
                code="timeout_error",
                statusCode=None,
                requestId=None,
                details=capture_provider_error_details(error=exc, secrets=self._error_secrets()),
            )
        except httpx.HTTPError as exc:
            error = ProviderTransportError(
                code="connection_error",
                statusCode=None,
                requestId=None,
                details=capture_provider_error_details(error=exc, secrets=self._error_secrets()),
            )
        if error is not None:
            self._log_provider_error(error)
            raise error
        if response is None:
            raise RuntimeError("索引供应商未返回响应")
        if not response.is_success:
            http_error = ProviderTransportError(
                code="http_error",
                statusCode=response.status_code,
                requestId=None,
                details=capture_provider_error_details(
                    response=response, secrets=self._error_secrets()
                ),
            )
            self._log_provider_error(http_error)
            raise http_error
        invalid_json = False
        json_error_details = None
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            json_error_details = capture_provider_error_details(
                response=response,
                error=exc,
                secrets=self._error_secrets(),
                include_success_body=True,
            )
            invalid_json = True
            body = None
        if invalid_json:
            json_error = ProviderProtocolError(
                code="invalid_response_json",
                statusCode=response.status_code,
                requestId=None,
                details=json_error_details,
            )
            self._log_provider_error(json_error)
            raise json_error
        input_tokens = _input_tokens(body)
        if input_tokens is None:
            self._log_failure(
                "embedding_usage", {"usage": body.get("usage") if isinstance(body, dict) else None}
            )
        data = body.get("data") if isinstance(body, dict) else None
        if (
            not isinstance(data, list)
            or len(data) != len(request.texts)
            or any(
                not isinstance(item, dict) or type(item.get("index")) is not int for item in data
            )
            or {item["index"] for item in data} != set(range(len(request.texts)))
        ):
            self._log_failure("embedding_envelope", body)
            return EmbeddingResult(None, input_tokens, "EMBEDDING_OUTPUT_INVALID")
        try:
            output = RagEmbeddingBatchOutput(
                embeddings=[
                    item.get("embedding") for item in sorted(data, key=lambda item: item["index"])
                ]
            )
        except ValidationError as exc:
            self._log_failure(
                "embedding_schema",
                {
                    "response": body,
                    "schema": RagEmbeddingBatchOutput.model_json_schema(),
                    "validationErrors": exc.errors(include_url=False),
                },
                exc,
            )
            return EmbeddingResult(None, input_tokens, "EMBEDDING_OUTPUT_INVALID")
        return EmbeddingResult(output.embeddings, input_tokens)


def _input_tokens(body: object) -> int | None:
    if not isinstance(body, dict) or not isinstance(body.get("usage"), dict):
        return None
    usage = body["usage"]
    prompt = usage.get("prompt_tokens")
    if type(prompt) is not int or prompt < 0:
        return None
    if "total_tokens" in usage and (
        type(usage["total_tokens"]) is not int or usage["total_tokens"] != prompt
    ):
        return None
    return prompt
