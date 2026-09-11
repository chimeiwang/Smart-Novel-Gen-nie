from __future__ import annotations

from inkforge_cli.commands.long.video import VIDEO_COMMAND_SPECS


def test_video_registry_keeps_only_shared_project_asset_canon_and_episode_native_domains() -> None:
    names = {spec.name for spec in VIDEO_COMMAND_SPECS}

    assert {
        "long.video.project.list",
        "long.video.project.get",
        "long.video.project.create",
        "long.video.asset.upload",
        "long.video.asset.rights",
        "long.video.asset.download",
        "long.video.asset.preview",
        "long.video.canon.list",
        "long.video.canon.candidate.set",
        "long.video.canon.approve",
    } <= names
    assert not any(
        name.startswith(prefix)
        for name in names
        for prefix in (
            "long.video.adaptation.",
            "long.video.plan.",
            "long.video.prompt.",
            "long.video.reference.",
            "long.video.render.",
            "long.video.take.",
            "long.video.post.",
            "long.video.keyframe.",
            "long.video.edit.",
            "long.video.mix.",
            "long.video.export.",
        )
    )
    assert all(
        name.startswith("long.video.episode.")
        or name.startswith("long.video.project.")
        or name.startswith("long.video.asset.")
        or name.startswith("long.video.canon.")
        or name == "long.video.production.capabilities.get"
        for name in names
    )
