from inkforge_agents.runtime.turn_result import aggregate_visible_content


def test_visible_content_is_never_silently_truncated() -> None:
    parts = ["甲" * 100_000, "乙" * 100_000]

    assert aggregate_visible_content(parts) == parts[0] + "\n\n" + parts[1]
