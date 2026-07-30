from __future__ import annotations

from inkforge_core.short_medium.schemas import build_document_diff


def test_diff_keeps_unicode_and_tail_without_truncation() -> None:
    before = "第一段😀\n\n" + "旧内容" * 20_000 + "\n\n旧尾部"
    after = "第一段😀\n\n" + "新内容" * 20_000 + "\n\n八万字尾部标记"

    result = build_document_diff(
        before,
        after,
        from_version_id="version-1",
        to_version_id="version-2",
    )

    assert result.fromVersionId == "version-1"
    assert result.toVersionId == "version-2"
    assert any("八万字尾部标记" in (block.newText or "") for block in result.blocks)
    assert result.toWordCount > 0
    assert result.wordCountDelta == result.toWordCount - result.fromWordCount
    assert len(result.confirmationHash) == 64


def test_diff_only_returns_changed_blocks() -> None:
    result = build_document_diff(
        "相同段\n\n旧段",
        "相同段\n\n新段",
        from_version_id="version-1",
        to_version_id="version-2",
    )

    assert result.blocks
    assert all(block.type != "equal" for block in result.blocks)
    assert result.blocks[-1].oldText == "旧段"
    assert result.blocks[-1].newText == "新段"
