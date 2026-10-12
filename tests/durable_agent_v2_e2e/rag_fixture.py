"""隔离 embeddings HTTP 供应商使用完整分块，不经过聊天 Fake。"""

from __future__ import annotations

import hashlib
import json

MODEL = "e2e-embedding-vector-v1"
BASE_URL = "http://e2e-control:8090"
ENDPOINT_KEY = (
    "endpoint.rag-embedding."
    + hashlib.sha256((BASE_URL + "/v1/embeddings").encode()).hexdigest()
    + ".v1"
)
# 每块带不同标记；保留 BOM、CRLF、补充平面字符和边缘空白，共 11 块、两批。
CONTENT = "\ufeff" + "".join(f"{index:05d}甲😀\r\n\u00a0" for index in range(1900)) + " 尾部\t\n"
CHUNKS = tuple(CONTENT[index : index + 1800] for index in range(0, len(CONTENT), 1800))
BATCHES = tuple(CHUNKS[index : index + 10] for index in range(0, len(CHUNKS), 10))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(value + 1) / 256 for value in digest[:3]]


def batch_body(batch: tuple[str, ...]) -> dict[str, object]:
    return {"model": MODEL, "input": list(batch)}


def request_hash(body: dict[str, object]) -> str:
    return sha(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def embedding_response(body: object) -> tuple[dict[str, str], dict[str, object]]:
    if not isinstance(body, dict) or set(body) != {"model", "input"} or body["model"] != MODEL:
        raise ValueError("隔离 embeddings 只接收真实 model 与 input，不接受聊天或业务身份信封")
    texts = body["input"]
    if not isinstance(texts, list) or texts not in [list(batch) for batch in BATCHES]:
        raise ValueError("隔离 embeddings 输入不是完整原文重建的有序批次")
    digest = request_hash(body)
    # 此键仅供测试控制器计数，不发给供应商，也不声明供应商支持请求幂等。
    identity = {"idempotencyKey": "embedding." + digest, "requestSha256": digest}
    tokens = sum(len(text) for text in texts)
    return identity, {
        "object": "list",
        "model": MODEL,
        # 逆序响应迫使真实客户端按 index 重建，而非信任返回顺序。
        "data": [
            {"object": "embedding", "index": index, "embedding": embedding(texts[index])}
            for index in reversed(range(len(texts)))
        ],
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }
