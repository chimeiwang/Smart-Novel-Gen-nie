from inkforge_agents.graph.context import build_operation_context, parse_chapter_target
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS


def test_context_preserves_full_text_without_truncation() -> None:
    long_text = "正文" * 100_000
    context = build_operation_context(
        OPERATION_DEFINITIONS["write_chapter"],
        {"chapterContent": long_text, "chapterGoal": "推进主线"},
    )

    assert long_text in context[0]


def test_chapter_target_parser_distinguishes_current_and_next_chapter() -> None:
    assert parse_chapter_target("请重写当前章") == "current_chapter"
    assert parse_chapter_target("继续写下一章") == "next_chapter"
    assert parse_chapter_target("写一点内容") is None
