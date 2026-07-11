from __future__ import annotations

from typing import Any, Protocol

import httpx

from ..clients.core import RunResource
from ..queue.repository import QueueJob


class RagCorePort(Protocol):
    async def get_rag_context(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
    ) -> dict[str, Any]: ...

    async def complete_rag(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
        embeddings: list[list[float]],
    ) -> None: ...

    async def fail_rag(
        self,
        resource: RunResource,
        reference_id: str,
        content_hash: str,
        message: str,
    ) -> None: ...


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class RagJobHandler:
    def __init__(self, core: RagCorePort, embeddings: EmbeddingPort) -> None:
        self._core = core
        self._embeddings = embeddings

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "rag":
            raise ValueError("检索索引处理器收到错误任务类型")
        reference_id = job.payload.get("referenceId")
        content_hash = job.payload.get("contentHash")
        if not isinstance(reference_id, str) or not reference_id:
            raise ValueError("检索索引任务缺少参考资料标识")
        if not isinstance(content_hash, str) or not content_hash:
            raise ValueError("检索索引任务缺少内容哈希")
        resource = RunResource(
            userId=job.userId,
            novelId=job.novelId,
            taskId=job.taskId,
            runId=job.runId,
        )
        context = await self._core.get_rag_context(resource, reference_id, content_hash)
        chunks = context.get("chunks")
        if not isinstance(chunks, list) or any(not isinstance(item, str) for item in chunks):
            raise ValueError("核心服务返回的索引分块无效")
        texts = list(chunks)
        try:
            vectors = await self._embeddings.embed(texts)
            if len(vectors) != len(texts):
                raise RuntimeError("嵌入向量数量与索引分块数量不一致")
        except Exception as exc:
            await self._core.fail_rag(resource, reference_id, content_hash, str(exc))
            raise
        await self._core.complete_rag(resource, reference_id, content_hash, vectors)


class OpenAIEmbeddingProvider:
    def __init__(self, http: httpx.AsyncClient, *, model: str, batch_size: int = 10) -> None:
        if not model or batch_size < 1:
            raise ValueError("嵌入模型配置无效")
        self._http = http
        self._model = model
        self._batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for index in range(0, len(texts), self._batch_size):
            response = await self._http.post(
                "/embeddings",
                json={"model": self._model, "input": texts[index : index + self._batch_size]},
            )
            response.raise_for_status()
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            if not isinstance(data, list):
                raise RuntimeError("嵌入服务返回格式无效")
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            for item in ordered:
                vector = item.get("embedding") if isinstance(item, dict) else None
                if (
                    not isinstance(vector, list)
                    or not vector
                    or any(
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        for value in vector
                    )
                ):
                    raise RuntimeError("嵌入服务返回了无效向量")
                vectors.append([float(value) for value in vector])
        if len(vectors) != len(texts):
            raise RuntimeError("嵌入服务返回数量与请求数量不一致")
        return vectors
