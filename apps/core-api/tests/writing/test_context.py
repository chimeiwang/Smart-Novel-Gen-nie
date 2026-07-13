import pytest
from inkforge_core.errors import ApiError
from inkforge_core.writing.context import (
    ChapterGroupSnapshot,
    WritingContextService,
    select_unique_chapter_group,
)


def test_chapter_group_allows_missing_but_rejects_ambiguous_mapping() -> None:
    matching = ChapterGroupSnapshot("group-1", "第一组", 1, 5, "完整章节组内容")
    assert select_unique_chapter_group(3, [matching]) == matching
    assert select_unique_chapter_group(3, []) is None
    with pytest.raises(ApiError, match="没有唯一对应的章节组"):
        select_unique_chapter_group(
            3,
            [matching, ChapterGroupSnapshot("group-2", "重叠组", 3, 6, "冲突")],
        )


class FakePlanningRepository:
    async def get_planning_context(self, user_id: str, task_id: str):
        assert (user_id, task_id) == ("user-1", "task-1")
        return {
            "taskId": task_id,
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "chapterOrder": 3,
            "chapterGoal": {"narrativeGoal": "推进冲突"},
            "approvedBeatPlan": {"chapterGoal": "按计划推进", "sceneBeats": []},
            "chapterGroup": {"id": "group-1", "content": "完整章节组内容"},
            "outlinePath": [{"kind": "stage", "title": "第一卷"}],
            "activeArtifact": None,
        }


class FakeWorkspaceRepository:
    async def get_workspace(self, novel_id: str, user_id: str, chapter_id: str | None = None):
        assert (novel_id, user_id) == ("novel-1", "user-1")
        assert chapter_id == "chapter-1"
        return {"novel": {"id": novel_id, "name": "作品"}, "characters": []}


@pytest.mark.asyncio
async def test_context_combines_complete_workspace_and_current_planning_scope() -> None:
    context = await WritingContextService(
        FakePlanningRepository(), FakeWorkspaceRepository()
    ).build("user-1", "task-1")

    assert context["workspace"]["novel"]["name"] == "作品"
    assert context["planning"]["approvedBeatPlan"]["chapterGoal"] == "按计划推进"
    assert context["planning"]["chapterGroup"]["content"] == "完整章节组内容"
