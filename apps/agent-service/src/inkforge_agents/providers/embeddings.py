"""V2 独立 embedding 单 HTTP 适配，不改变旧 embed/query 客户端。"""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import httpx
from inkforge_contracts.rag_execution import RagEmbeddingBatchOutput
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .base import ProviderProtocolError, ProviderTransportError


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

    async def embed_batch(self, request: EmbeddingRequest) -> EmbeddingResult:
        response: httpx.Response | None = None
        error: ProviderTransportError | None = None
        try:
            response = await self._http.post(
                self._endpoint, json={"model": self.identity.model, "input": request.texts}
            )
        except httpx.TimeoutException:
            error = ProviderTransportError(code="timeout_error", statusCode=None, requestId=None)
        except httpx.HTTPError:
            error = ProviderTransportError(code="connection_error", statusCode=None, requestId=None)
        if error is not None:
            raise error
        if response is None:
            raise RuntimeError("索引供应商未返回响应")
        if not response.is_success:
            raise ProviderTransportError(
                code="http_error", statusCode=response.status_code, requestId=None
            )
        invalid_json = False
        try:
            body = response.json()
        except (ValueError, UnicodeError):
            invalid_json = True
            body = None
        if invalid_json:
            raise ProviderProtocolError(
                code="invalid_response_json", statusCode=response.status_code, requestId=None
            )
        input_tokens = _input_tokens(body)
        data = body.get("data") if isinstance(body, dict) else None
        if (
            not isinstance(data, list)
            or len(data) != len(request.texts)
            or any(
                not isinstance(item, dict) or type(item.get("index")) is not int for item in data
            )
            or {item["index"] for item in data} != set(range(len(request.texts)))
        ):
            return EmbeddingResult(None, input_tokens, "EMBEDDING_OUTPUT_INVALID")
        try:
            output = RagEmbeddingBatchOutput(
                embeddings=[
                    item.get("embedding") for item in sorted(data, key=lambda item: item["index"])
                ]
            )
        except ValidationError:
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
