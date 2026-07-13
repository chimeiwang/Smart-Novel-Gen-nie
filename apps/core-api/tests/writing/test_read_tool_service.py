from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_contracts.read_tools import READ_TOOL_NAMES
from inkforge_core.errors import ApiError
from inkforge_core.writing.read_tool_service import WritingReadToolService
from inkforge_core.writing.tool_gateway import ToolRequest


class FakeContext:
    async def build(self, user_id: str, task_id: str) -> dict[str, Any]:
        assert (user_id, task_id) == ("user-1", "task-1")
        return {
            "planning": {
                "novelId": "novel-1",
                "chapterId": "chapter-3",
                "chapterOrder": 3,
                "chapterGroup": {"id": "group-1", "title": "第一幕", "content": "章节组全文"},
                "outlinePath": [{"id": "stage-1", "title": "开端", "kind": "stage"}],
                "activeArtifact": {"id": "artifact-1"},
            },
            "workspace": {
                "novel": {
                    "id": "novel-1",
                    "name": "测试小说",
                    "summary": "小说简介",
                    "storyProgress": "推进到第三章",
                    "appliedStyleId": "style-1",
                },
                "currentChapterId": "chapter-3",
                "chapters": [
                    {"id": "chapter-1", "title": "第一章", "order": 1, "content": "甲" * 5000},
                    {"id": "chapter-2", "title": "第二章", "order": 2, "content": "乙" * 6000},
                    {"id": "chapter-3", "title": "第三章", "order": 3, "content": "当前章"},
                ],
                "characters": [
                    {
                        "id": "character-1",
                        "name": "沈墨",
                        "aliases": "阿墨",
                        "identity": "铸字师",
                        "personality": "谨慎",
                        "coreDesire": "找回真相",
                        "behaviorBoundaries": "不伤无辜",
                        "shortTermGoal": "进入藏书楼",
                        "currentStatus": "active",
                        "statusNote": None,
                        "faction": {"id": "faction-1", "name": "墨门"},
                        "experiences": [],
                        "outgoingRelations": [],
                        "incomingRelations": [],
                    }
                ],
                "factions": [{"id": "faction-1", "name": "墨门", "description": "守护文字"}],
                "locations": [{"id": "location-1", "name": "藏书楼", "description": "古老高塔"}],
                "items": [{"id": "item-1", "name": "墨印", "effect": "记录真名"}],
                "glossaries": [{"id": "term-1", "term": "铸字", "definition": "文字成真"}],
                "storyBackground": {"content": "故事背景全文"},
                "worldSetting": {"content": "世界设定全文"},
                "writingBible": {"storyLengthProfile": "long_serial"},
                "outline": {"content": "总纲全文"},
                "outlineNodes": [
                    {
                        "id": "stage-1",
                        "title": "开端",
                        "kind": "stage",
                        "status": "in_progress",
                        "order": 1,
                        "parentId": None,
                        "content": "阶段全文",
                    }
                ],
                "plotProgress": {"currentStage": "开端", "currentGoal": "进入藏书楼"},
                "references": [{"id": "reference-1", "title": "文字史", "content": "参考全文"}],
                "styles": [
                    {
                        "id": "style-1",
                        "name": "冷峻克制",
                        "portraitMarkdown": "文风画像全文",
                        "sourceType": "agent",
                    }
                ],
            },
        }


class FakeOutline:
    async def list_foreshadowings(self, novel_id: str, user_id: str) -> list[dict[str, Any]]:
        assert (novel_id, user_id) == ("novel-1", "user-1")
        return [
            {
                "id": "foreshadowing-1",
                "name": "断裂的墨印",
                "status": "planted",
                "plantedContent": "第一章埋下",
                "expectedPayoff": "终局回收",
                "createdAt": datetime(2026, 7, 12, tzinfo=UTC),
            }
        ]


class FakeReview:
    async def list_task_artifacts(
        self, user_id: str, novel_id: str, task_id: str, status: str | None, kind: str | None
    ) -> list[dict[str, Any]]:
        assert (user_id, novel_id, task_id) == ("user-1", "novel-1", "task-1")
        del status, kind
        return [{"id": "artifact-1", "taskId": "task-1", "novelId": "novel-1"}]

    async def get_response(self, user_id: str, artifact_id: str) -> dict[str, Any]:
        assert user_id == "user-1"
        return {
            "id": artifact_id,
            "taskId": "task-1",
            "novelId": "novel-1",
            "kind": "chapter_draft",
            "status": "under_review",
            "payload": {"kind": "chapter_draft", "content": "草案全文"},
        }


class FakeSemanticSearch:
    async def search(
        self, user_id: str, novel_id: str, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        assert (user_id, novel_id, embedding, top_k) == (
            "user-1",
            "novel-1",
            [0.1, 0.2],
            5,
        )
        return [{"title": "文字史", "text": "语义命中全文", "score": 0.9}]


def tool_request(name: str, arguments: dict[str, Any] | None = None) -> ToolRequest:
    return ToolRequest(
        user_id="user-1",
        novel_id="novel-1",
        task_id="task-1",
        run_id="run-1",
        agent_id="写作",
        tool_name=name,
        arguments=arguments or {},
    )


def service() -> WritingReadToolService:
    return WritingReadToolService(FakeContext(), FakeOutline(), FakeReview(), FakeSemanticSearch())


@pytest.mark.asyncio
async def test_all_registered_read_tools_have_executable_behavior() -> None:
    arguments = {
        "get_novel_info": {"include_full_sections": True},
        "get_character_detail": {"character_name": "沈墨"},
        "get_faction_detail": {"faction_name": "墨门"},
        "get_location_detail": {"location_name": "藏书楼"},
        "get_item_detail": {"item_name": "墨印"},
        "get_glossary_detail": {"term": "铸字"},
        "search_lore": {"keyword": "文字"},
        "find_similar_lore": {"keyword": "墨门"},
        "semantic_search_references": {
            "query": "文字",
            "topK": 5,
            "query_embedding": [0.1, 0.2],
        },
        "list_outline_summary": {"scope": "tree_index", "include_full_summary": True},
        "get_outline_node": {"node_id": "stage-1"},
        "get_foreshadowing_detail": {"foreshadowing_name": "断裂的墨印"},
        "get_recent_chapters": {"count": 2},
        "get_review_artifact": {"artifact_id": "artifact-1"},
    }

    results = {
        name: await service().execute(tool_request(name, arguments.get(name)))
        for name in READ_TOOL_NAMES
    }

    assert set(results) == set(READ_TOOL_NAMES)
    assert all(isinstance(result, dict) for result in results.values())
    assert results["get_novel_info"]["worldSetting"] == "世界设定全文"
    assert results["get_character_detail"]["character"]["name"] == "沈墨"
    assert results["semantic_search_references"]["results"][0]["text"] == "语义命中全文"


@pytest.mark.asyncio
async def test_recent_chapters_returns_complete_content_before_target_chapter() -> None:
    result = await service().execute(tool_request("get_recent_chapters", {"count": 2}))

    assert [chapter["id"] for chapter in result["chapters"]] == ["chapter-1", "chapter-2"]
    assert result["chapters"][1]["content"] == "乙" * 6000


@pytest.mark.asyncio
async def test_repository_datetimes_are_converted_to_json_values() -> None:
    result = await service().execute(
        tool_request("get_foreshadowing_detail", {"foreshadowing_name": "断裂的墨印"})
    )

    assert result["foreshadowing"]["createdAt"] == "2026-07-12T00:00:00Z"


@pytest.mark.asyncio
async def test_review_artifact_must_belong_to_current_task() -> None:
    review = FakeReview()

    async def wrong_task(user_id: str, artifact_id: str) -> dict[str, Any]:
        del user_id, artifact_id
        return {"id": "artifact-2", "taskId": "task-2", "novelId": "novel-1"}

    review.get_response = wrong_task  # type: ignore[method-assign]
    subject = WritingReadToolService(FakeContext(), FakeOutline(), review, FakeSemanticSearch())

    with pytest.raises(ApiError) as error:
        await subject.execute(tool_request("get_review_artifact", {"artifact_id": "artifact-2"}))

    assert error.value.status_code == 403
    assert error.value.code == "ARTIFACT_TASK_MISMATCH"
