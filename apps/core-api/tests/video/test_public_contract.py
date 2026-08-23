from __future__ import annotations

from inkforge_core.app import create_app

EXPECTED_VIDEO_PATHS = {
    "/api/v1/video/novels/{novel_id}/projects",
    "/api/v1/video/projects/{project_id}",
    "/api/v1/video/projects/{project_id}/assets",
    "/api/v1/video/assets/{asset_id}/rights",
    "/api/v1/video/assets/{asset_id}/content",
    "/api/v1/video/assets/{asset_id}/preview",
    "/api/v1/video/projects/{project_id}/chapter-adaptations",
    "/api/v1/video/projects/{project_id}/visual-canons",
    "/api/v1/video/visual-canons/{canon_id}/approve",
    "/api/v1/video/chapter-adaptations/{adaptation_id}",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan-runs",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan/confirm",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/candidate/discard",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/episode-plan",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/prompt-runs",
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/prompt",
    (
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/"
        "{shot_id}/visual-references"
    ),
}


def test_remaining_public_video_paths_are_exact() -> None:
    """旧 VideoScene 路由退役后只允许当前产品链进入 OpenAPI。"""

    document = create_app(testing=True).openapi()
    paths = {
        path
        for path in document["paths"]
        if path.startswith("/api/v1/video/")
    }
    operation_count = sum(
        method in {"get", "post", "put", "patch", "delete"}
        for path, path_item in document["paths"].items()
        if path.startswith("/api/v1/video/")
        for method in path_item
    )

    assert paths == EXPECTED_VIDEO_PATHS
    assert operation_count == 20
    assert not any("/scenes" in path for path in paths)


def test_legacy_video_scene_contracts_are_absent_from_openapi() -> None:
    """历史兼容 Python 类型不能重新泄漏为浏览器公共契约。"""

    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    forbidden = {
        "ApproveVideoSceneRequest",
        "ApproveVideoSceneResponse",
        "CreateVideoSceneRequest",
        "CreateVideoSceneResponse",
        "PromptPreviewRequest",
        "PromptPreviewResponse",
        "ReviseVideoSceneRequest",
        "VideoSceneResponse",
    }

    assert forbidden.isdisjoint(schemas)
    assert "sceneCount" not in schemas["VideoProjectResponse"]["properties"]
    assert "scenes" not in schemas["VideoProjectDetailResponse"]["properties"]
