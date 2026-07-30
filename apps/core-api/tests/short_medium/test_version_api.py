from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser

NOW = datetime(2026, 7, 30, tzinfo=UTC)


class FakeVersionService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def list_versions(
        self, user_id: str, novel_id: str, document_type: str, chapter_id: str | None
    ) -> list[dict[str, object]]:
        self.calls.append(("list", user_id, novel_id, document_type, chapter_id))
        return [
            {
                "id": "version-1",
                "documentType": document_type,
                "versionNumber": 1,
                "status": "applied",
                "source": "manual",
                "wordCount": 4,
                "baseVersionId": None,
                "sourceOutlineVersionId": None,
                "restoredFromVersionId": None,
                "summary": None,
                "createdByAgent": None,
                "createdAt": NOW,
                "updatedAt": NOW,
                "appliedAt": NOW,
            }
        ]

    async def preview(
        self, user_id: str, novel_id: str, body: object
    ) -> dict[str, object]:
        self.calls.append(("preview", user_id, novel_id, body))
        return {
            "documentType": "outline",
            "chapterId": None,
            "baseVersionId": None,
            "expectedUpdatedAt": NOW,
            "contentHash": "a" * 64,
            "dirty": True,
            "confirmationSummary": "确认提交",
            "confirmationHash": "b" * 64,
            "diff": {
                "fromVersionId": None,
                "toVersionId": None,
                "fromWordCount": 0,
                "toWordCount": 4,
                "wordCountDelta": 4,
                "blocks": [],
                "confirmationHash": "b" * 64,
            },
        }


@asynccontextmanager
async def version_client(
    service: FakeVersionService,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(testing=True)
    app.state.short_medium_version_service = service
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="author",
        password_hash="仅测试占位值",  # noqa: S106
        credit_balance_micros=0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_version_list_uses_authenticated_owner_and_explicit_document() -> None:
    service = FakeVersionService()
    async with version_client(service) as client:
        response = await client.get(
            "/api/v1/novels/novel-1/versions",
            params={"documentType": "outline"},
        )

    assert response.status_code == 200
    assert response.json()[0]["versionNumber"] == 1
    assert service.calls == [("list", "user-1", "novel-1", "outline", None)]


@pytest.mark.asyncio
async def test_preview_contract_parses_camel_case_request_without_full_content() -> None:
    service = FakeVersionService()
    async with version_client(service) as client:
        response = await client.post(
            "/api/v1/novels/novel-1/versions/preview",
            json={
                "documentType": "outline",
                "chapterId": None,
                "baseVersionId": None,
            },
        )

    assert response.status_code == 200
    assert response.json()["contentHash"] == "a" * 64
    body = service.calls[0][-1]
    assert not hasattr(body, "content")


def test_openapi_exposes_all_short_medium_version_routes() -> None:
    paths = create_app(testing=True).openapi()["paths"]

    assert "/api/v1/novels/{novel_id}/versions" in paths
    assert "/api/v1/novels/{novel_id}/versions/preview" in paths
    assert "/api/v1/novels/{novel_id}/versions/{version_id}" in paths
    assert "/api/v1/novels/{novel_id}/versions/{version_id}/adopt" in paths
    assert "/api/v1/novels/{novel_id}/versions/{version_id}/restore" in paths
    assert "/api/v1/novels/{novel_id}/version-diff" in paths
