from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_core.config import Settings


class Verifier:
    def __init__(self) -> None:
        self.kwargs = None

    async def verify_request(self, **kwargs):
        self.kwargs = kwargs
        return object()


class Service:
    async def get_portrait_context(self, style_id: str, task_id: str):
        assert (style_id, task_id) == ("style-1", "task-1")
        return {"sourceText": "完整参考正文", "originalCharCount": 6}


def test_portrait_context_uses_signed_internal_boundary() -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            trusted_agent_cidrs=("127.0.0.1/32",),
        )
    )
    verifier = Verifier()
    app.state.rag_callback_verifier = verifier
    app.state.style_service = Service()
    body = b'{"runId":"task-1"}'

    response = TestClient(app, client=("127.0.0.1", 50000)).post(
        "/internal/v1/styles/style-1/portrait-tasks/task-1/portrait-context",
        content=body,
        headers={
            "Authorization": "Bearer signed",
            "Idempotency-Key": "portrait-context-1",
            "X-InkForge-Timestamp": "1",
            "X-InkForge-Body-SHA256": hashlib.sha256(body).hexdigest(),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "sourceText": "完整参考正文",
        "originalCharCount": 6,
    }
    assert verifier.kwargs["required_scope"] is ServiceScope.PORTRAIT_WRITE
    assert verifier.kwargs["task_id"] == "task-1"
    assert verifier.kwargs["novel_id"] == "style:style-1"
