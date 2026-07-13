from inkforge_agents.artifacts.builder import resolve_builder_artifact


def test_builder_merges_outline_tree_and_full_text_block() -> None:
    events = [
        {
            "type": "start_update_builder",
            "artifactKey": "outline-1",
            "summary": "重构大纲",
        },
        {
            "type": "append_outline_tree",
            "artifactKey": "outline-1",
            "mode": "replace",
            "stages": [
                {
                    "title": "第一卷",
                    "chapterStartOrder": 1,
                    "chapterEndOrder": 20,
                    "plotUnits": [
                        {
                            "title": "危机",
                            "chapterStartOrder": 1,
                            "chapterEndOrder": 20,
                            "chapterGroups": [
                                {
                                    "title": "开端",
                                    "chapterStartOrder": 1,
                                    "chapterEndOrder": 5,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "type": "put_update_text_block",
            "artifactKey": "outline-1",
            "section": "outlineContent",
        },
        {
            "type": "finish_update_builder",
            "artifactKey": "outline-1",
            "summary": "完成大纲",
            "submitForReview": True,
        },
    ]
    visible = "说明\nARTIFACT_OUTPUT_START\n" + "完整总纲" * 3000 + "\nARTIFACT_OUTPUT_END"

    artifact = resolve_builder_artifact(events, visible)

    assert artifact is not None
    assert artifact["type"] == "propose_updates"
    assert artifact["summary"] == "完成大纲"
    assert artifact["updates"]["outlineTreeMode"] == "replace"
    assert artifact["updates"]["outlineContent"] == "完整总纲" * 3000
    adjustments = artifact["updates"]["outlineAdjustments"]
    assert [item["kind"] for item in adjustments] == [
        "stage",
        "plot_unit",
        "chapter_group",
    ]
    assert adjustments[1]["parentKey"] == adjustments[0]["clientKey"]
    assert adjustments[2]["parentKey"] == adjustments[1]["clientKey"]


def test_builder_treats_repeated_start_as_idempotent() -> None:
    artifact = resolve_builder_artifact(
        [
            {
                "type": "start_update_builder",
                "artifactKey": "task-1:sync_lore",
                "summary": "同步设定",
            },
            {
                "type": "append_update_batch",
                "artifactKey": "task-1:sync_lore",
                "updates": {"storyBackground": "第一批事实"},
            },
            {
                "type": "start_update_builder",
                "artifactKey": "task-1:sync_lore",
                "summary": "继续同步设定",
            },
            {
                "type": "append_update_batch",
                "artifactKey": "task-1:sync_lore",
                "updates": {"worldSetting": "第二批事实"},
            },
            {
                "type": "finish_update_builder",
                "artifactKey": "task-1:sync_lore",
                "summary": "同步完成",
            },
        ],
        "设定同步完成。",
    )

    assert artifact is not None
    assert artifact["updates"] == {
        "storyBackground": "第一批事实",
        "worldSetting": "第二批事实",
    }
