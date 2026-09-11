from __future__ import annotations

from inkforge_core.app import create_app

EXPECTED_VIDEO_PATHS = {
    "/api/v1/video/assets/{asset_id}/content",
    "/api/v1/video/assets/{asset_id}/preview",
    "/api/v1/video/assets/{asset_id}/rights",
    "/api/v1/video/episodes/{episode_id}",
    "/api/v1/video/episodes/{episode_id}/commands/{client_request_id}",
    "/api/v1/video/episodes/{episode_id}/impact-reviews",
    "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}",
    "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}/decisions",
    "/api/v1/video/episodes/{episode_id}/production-baselines",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions/{version_id}",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}/retry",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}/content",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions/{version_id}",
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/shots/{shot_id}/render-tasks",
    "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}",
    "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}/retry",
    "/api/v1/video/episodes/{episode_id}/script/candidates/{artifact_id}/adopt",
    "/api/v1/video/episodes/{episode_id}/script/confirmations",
    "/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}",
    "/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}/approve",
    "/api/v1/video/episodes/{episode_id}/script/draft",
    "/api/v1/video/episodes/{episode_id}/script/runs",
    "/api/v1/video/episodes/{episode_id}/script/runs/{run_id}",
    "/api/v1/video/episodes/{episode_id}/script/versions",
    "/api/v1/video/episodes/{episode_id}/script/versions/{version_id}",
    "/api/v1/video/episodes/{episode_id}/source-sets",
    "/api/v1/video/episodes/{episode_id}/source-sets/{version_id}",
    "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}",
    "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}/adopt",
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations",
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}",
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}/approve",
    "/api/v1/video/episodes/{episode_id}/storyboard/draft",
    "/api/v1/video/episodes/{episode_id}/storyboard/runs",
    "/api/v1/video/episodes/{episode_id}/storyboard/runs/{run_id}",
    "/api/v1/video/episodes/{episode_id}/storyboard/versions",
    "/api/v1/video/episodes/{episode_id}/storyboard/versions/{version_id}",
    "/api/v1/video/episodes/{episode_id}/take-adoptions",
    "/api/v1/video/episodes/{episode_id}/take-adoptions/{adoption_id}",
    "/api/v1/video/episodes/{episode_id}/takes",
    "/api/v1/video/episodes/{episode_id}/takes/{take_id}/content",
    "/api/v1/video/novels/{novel_id}/projects",
    "/api/v1/video/production-capabilities",
    "/api/v1/video/projects/{project_id}",
    "/api/v1/video/projects/{project_id}/assets",
    "/api/v1/video/projects/{project_id}/episode-commands/{client_request_id}",
    "/api/v1/video/projects/{project_id}/episodes",
    "/api/v1/video/projects/{project_id}/episodes/reorder",
    "/api/v1/video/projects/{project_id}/visual-canons",
    "/api/v1/video/visual-canons/{canon_id}/approve",
}


def test_remaining_public_video_paths_are_exact() -> None:
    """旧域退役后只允许 Episode 主链及 Project/Asset/VisualCanon 进入 OpenAPI。"""

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
    assert operation_count == 67
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


def test_episode_export_duty_is_output_only_in_public_contract() -> None:
    """浏览器可读成片职责，但不能把任意上传视频伪装成受控整集导出。"""

    schemas = create_app(testing=True).openapi()["components"]["schemas"]
    upload_duties = schemas[
        "Body_upload_asset_api_v1_video_projects__project_id__assets_post"
    ]["properties"]["duty"]["enum"]
    response_duties = schemas["VideoAssetResponse"]["properties"]["duty"]["enum"]

    assert "sfx" in upload_duties
    assert "episode_export" not in upload_duties
    assert "episode_export" in response_duties
