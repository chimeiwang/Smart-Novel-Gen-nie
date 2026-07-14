from __future__ import annotations

from datetime import timedelta
from typing import Any

import fakeredis.aioredis
from fastapi.testclient import TestClient
from inkforge_agents.app import create_app
from inkforge_agents.queue.repository import RedisRunQueue
from inkforge_contracts.jwt_claims import ServiceScope


class Verifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def verify_request(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return object()


def body() -> dict[str, object]:
    return {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "kind": "writing",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "userId": "user-1",
        "priority": 10,
        "payload": {"resume": False},
        "force": False,
    }


def test_signed_run_submission_verifies_binding_and_enqueues() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:runs")
    verifier = Verifier()
    client = TestClient(
        create_app(testing=True, run_queue=queue, core_request_verifier=verifier),
        client=("127.0.0.1", 50000),
    )
    with client:
        response = client.post(
            "/internal/v1/runs",
            json=body(),
            headers={
                "Authorization": "Bearer signed",
                "Idempotency-Key": "job-1",
                "X-InkForge-Timestamp": "1",
                "X-InkForge-Body-SHA256": "0" * 64,
            },
        )

        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert verifier.calls[0]["required_scope"] == ServiceScope.AGENT_RUN
        assert verifier.calls[0]["task_id"] == "task-1"
        claim = client.portal.call(lambda: queue.claim(visibility_timeout=timedelta(seconds=30)))
        assert claim is not None and claim.job.jobId == "job-1"


def test_run_submission_rejects_missing_bearer_before_queue_write() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:runs")
    response = TestClient(
        create_app(testing=True, run_queue=queue, core_request_verifier=Verifier()),
        client=("127.0.0.1", 50000),
    ).post("/internal/v1/runs", json=body())

    assert response.status_code == 401


def test_duplicate_run_submission_returns_existing_terminal_status() -> None:
    queue = RedisRunQueue(fakeredis.aioredis.FakeRedis(), prefix="test:runs")
    client = TestClient(
        create_app(testing=True, run_queue=queue, core_request_verifier=Verifier()),
        client=("127.0.0.1", 50000),
    )
    headers = {
        "Authorization": "Bearer signed",
        "Idempotency-Key": "job-1",
        "X-InkForge-Timestamp": "1",
        "X-InkForge-Body-SHA256": "0" * 64,
    }

    with client:
        assert client.post("/internal/v1/runs", json=body(), headers=headers).status_code == 202
        claim = client.portal.call(
            lambda: queue.claim(visibility_timeout=timedelta(seconds=30))
        )
        assert claim is not None
        assert client.portal.call(
            lambda: queue.acknowledge(claim, status="failed")
        )

        response = client.post("/internal/v1/runs", json=body(), headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "failed"
