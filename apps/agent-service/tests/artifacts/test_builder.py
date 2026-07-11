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
