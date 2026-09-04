"""正文 V2 编辑的独立 Unicode 回归，不改动 V1 或选区替换契约。"""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from inkforge_cli.commands.long import artifacts
from inkforge_cli.json_types import JsonObject
from inkforge_cli.runtime import CliInputError, CliRuntime


def _execute(content: str, field: str, path: Path) -> list[tuple[str, dict[str, object]]]:
    path.write_bytes(content.encode("utf-8"))
    calls: list[tuple[str, dict[str, object]]] = []

    def request(method: str, _path: str, **options: object) -> JsonObject:
        calls.append((method, options))
        if method == "GET":
            return {
                "id": "draft-1", "revision": 7, "engineVersion": 2,
                "sourceBindingStatus": "verified", "kind": "chapter_draft",
                "payload": {"operation": "write_chapter", "target": {"mode": "existing_chapter"}},
            }
        return {"runId": "run-1", "status": "completed"}

    runtime = cast(
        CliRuntime, SimpleNamespace(require_api=lambda: SimpleNamespace(request=request)),
    )
    payload: JsonObject = {
        "artifactId": "draft-1", "engineVersion": 2, "expectedRevision": 7,
        "clientRequestId": "unicode-chapter-edit-0001",
        field: str(path) if field.endswith("File") else content,
    }
    try:
        artifacts.approve(runtime, payload)
    except CliInputError:
        assert [method for method, _ in calls] == ["GET"]
        raise
    return calls


@pytest.mark.parametrize("field", ["editedContent", "editedContentFile"])
@pytest.mark.parametrize("content", ["\ufeff", " \n\t\u0085\u00a0\ufeff\u3000"])
def test_v2_chapter_edit_rejects_bom_only_or_blank_bom_mix(
    tmp_path: Path, field: str, content: str,
) -> None:
    with pytest.raises(CliInputError) as caught:
        _execute(content, field, tmp_path / "空白正文.txt")
    assert caught.value.code == "INVALID_EDITED_CONTENT"


@pytest.mark.parametrize("field", ["editedContent", "editedContentFile"])
def test_v2_chapter_edit_does_not_remove_bom_or_whitespace_from_nonblank_content(
    tmp_path: Path, field: str,
) -> None:
    content = "\ufeff  正文😀e\u0301\r\n\ufeff"
    calls = _execute(content, field, tmp_path / "完整正文.txt")
    assert calls[0][1] == {"params": {"revision": 7}}
    assert calls[-1][0] == "POST"
    assert cast(JsonObject, calls[-1][1]["json"])["editedContent"] == content


@pytest.mark.parametrize("content", ["\u001c", "\u001d", "\u001e", "\u001f"])
def test_v2_chapter_edit_uses_contract_whitespace_set(tmp_path: Path, content: str) -> None:
    calls = _execute(content, "editedContent", tmp_path / "控制码点.txt")
    assert cast(JsonObject, calls[-1][1]["json"])["editedContent"] == content
