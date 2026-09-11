from __future__ import annotations

from inkforge_cli.commands.long.video import VIDEO_COMMAND_SPECS


def test_legacy_video_watchers_leave_the_episode_native_cli() -> None:
    names = {spec.name for spec in VIDEO_COMMAND_SPECS}

    assert {
        "long.video.adaptation.watch",
        "long.video.render.watch",
        "long.video.export.watch",
    }.isdisjoint(names)
