from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser

NOW = datetime(2026, 7, 11, tzinfo=UTC)


class ApiStyleService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def list_styles(self, user_id):
        self.calls.append(("list", user_id))
        return []

    async def create_style(self, user_id, body):
        self.calls.append(("create", user_id, body.name))
        return {
            "id": "style-1",
            "name": body.name,
            "sourceType": "agent",
            "creativeMethodology": None,
            "uniqueMarkers": None,
            "generationStyle": None,
            "expressionFeatures": None,
            "styleTraits": None,
            "portraitMarkdown": None,
            "originalCharCount": 0,
            "usedCharCount": 0,
            "truncated": False,
            "errorMessage": None,
            "createdAt": NOW,
            "updatedAt": NOW,
            "references": [],
            "tasks": [],
        }

    async def delete_style(self, user_id, style_id):
        self.calls.append(("delete-style", user_id, style_id))

    async def upload_reference(self, user_id, style_id, file):
        self.calls.append(("upload", user_id, style_id, file.filename))
        return {
            "id": "ref-1",
            "styleId": style_id,
            "filename": file.filename,
            "charCount": 2,
            "status": "ready",
            "errorMessage": None,
            "createdAt": NOW,
        }

    async def delete_reference(self, user_id, style_id, reference_id):
        self.calls.append(("delete-ref", user_id, style_id, reference_id))

    async def create_portrait(self, user_id, style_id):
        self.calls.append(("portrait", user_id, style_id))
        return {"taskId": "task-1", "status": "pending"}

    async def get_portrait_task(self, user_id, task_id):
        self.calls.append(("get-task", user_id, task_id))
        return {
            "id": task_id,
            "styleId": "style-1",
            "status": "pending",
            "errorMessage": None,
            "createdAt": NOW,
            "updatedAt": NOW,
        }

    async def update_section(self, user_id, style_id, section, body):
        self.calls.append(("section", user_id, style_id, section, body.content))
        return await self.create_style(user_id, type("Body", (), {"name": "私有文风"})())

    async def apply_style(self, user_id, novel_id, body):
        self.calls.append(("apply", user_id, novel_id, body.styleId))


@asynccontextmanager
async def client(
    service: ApiStyleService, *, authenticated: bool = True
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(testing=True)
    app.state.style_service = service
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            id="cookie-user", username="alice", password_hash="", credit_balance_micros=0
        )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/v1/styles", {}),
        ("POST", "/api/v1/styles", {"json": {"name": "文风"}}),
        ("DELETE", "/api/v1/styles/style-1", {}),
        (
            "POST",
            "/api/v1/styles/style-1/references",
            {"files": {"file": ("a.txt", b"a", "text/plain")}},
        ),
        ("DELETE", "/api/v1/styles/style-1/references/ref-1", {}),
        ("POST", "/api/v1/styles/style-1/portrait", {}),
        ("GET", "/api/v1/portrait-tasks/task-1", {}),
        (
            "PATCH",
            "/api/v1/styles/style-1/sections/styleTraits",
            {"json": {"content": "特质"}},
        ),
        (
            "PATCH",
            "/api/v1/novels/novel-1/applied-style",
            {"json": {"styleId": None}},
        ),
    ],
)
async def test_public_style_routes_require_browser_session(
    method: str, path: str, kwargs: dict[str, object]
) -> None:
    async with client(ApiStyleService(), authenticated=False) as value:
        response = await value.request(method, path, **kwargs)
        assert response.status_code in {401, 503}


@pytest.mark.asyncio
async def test_public_style_route_matrix_and_multipart_upload() -> None:
    service = ApiStyleService()
    async with client(service) as value:
        assert (await value.get("/api/v1/styles")).status_code == 200
        assert (await value.post("/api/v1/styles", json={"name": "共享文风"})).status_code == 201
        assert (
            await value.post(
                "/api/v1/styles/style-1/references",
                files={"file": ("作品.TXT", "正文".encode(), "text/plain")},
            )
        ).status_code == 201
        assert (await value.delete("/api/v1/styles/style-1/references/ref-1")).status_code == 204
        assert (await value.post("/api/v1/styles/style-1/portrait")).status_code == 202
        assert (await value.get("/api/v1/portrait-tasks/task-1")).status_code == 200
        assert (
            await value.patch(
                "/api/v1/styles/style-1/sections/styleTraits", json={"content": "特质"}
            )
        ).status_code == 200
        assert (
            await value.patch("/api/v1/novels/novel-1/applied-style", json={"styleId": None})
        ).status_code == 204
        assert (await value.delete("/api/v1/styles/style-1")).status_code == 204
    assert ("apply", "cookie-user", "novel-1", None) in service.calls
    assert ("list", "cookie-user") in service.calls
    assert ("create", "cookie-user", "共享文风") in service.calls
    assert ("delete-style", "cookie-user", "style-1") in service.calls
    assert ("upload", "cookie-user", "style-1", "作品.TXT") in service.calls
    assert ("delete-ref", "cookie-user", "style-1", "ref-1") in service.calls
    assert ("get-task", "cookie-user", "task-1") in service.calls
    assert ("section", "cookie-user", "style-1", "styleTraits", "特质") in service.calls


def test_openapi_publishes_strict_dtos_and_hides_internal_callbacks() -> None:
    schema = create_app(testing=True).openapi()
    paths = schema["paths"]
    assert "/api/v1/styles" in paths
    assert "/api/v1/styles/{style_id}/references" in paths
    assert "/api/v1/styles/{style_id}/portrait" in paths
    assert "/api/v1/portrait-tasks/{task_id}" in paths
    assert "/api/v1/novels/{novel_id}/applied-style" in paths
    assert not any(path.startswith("/internal/") for path in paths)
    for name in ("CreateStyleRequest", "UpdatePortraitSectionRequest", "ApplyStyleRequest"):
        assert schema["components"]["schemas"][name]["additionalProperties"] is False
    assert "filepath" not in schema["components"]["schemas"]["StyleReferenceResponse"][
        "properties"
    ]
    task_status = schema["components"]["schemas"]["PortraitTaskResponse"]["properties"]["status"]
    assert task_status["enum"] == [
        "pending",
        "processing",
        "success",
        "error",
    ]
