from __future__ import annotations

import json
from pathlib import Path

import pytest
from inkforge_cli.files import (
    DirtySnapshotError,
    atomic_write_text,
    export_snapshot,
    sha256_text,
    write_large_result,
)


def test_pull_refuses_to_overwrite_a_locally_modified_document(tmp_path: Path) -> None:
    export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="旧大纲",
        manuscript="旧正文",
        metadata={"outlineUpdatedAt": "v1", "manuscriptUpdatedAt": "v1"},
    )
    (tmp_path / "outline.md").write_text("本地未同步修改", encoding="utf-8")

    with pytest.raises(DirtySnapshotError):
        export_snapshot(
            tmp_path,
            novel_id="novel-1",
            outline="服务端新大纲",
            manuscript="服务端新正文",
            metadata={"outlineUpdatedAt": "v2", "manuscriptUpdatedAt": "v2"},
        )

    assert (tmp_path / "outline.md").read_text(encoding="utf-8") == "本地未同步修改"


@pytest.mark.parametrize(
    "mutate_manifest",
    [
        lambda manifest, root: manifest["documents"].pop("outline"),
        lambda manifest, root: manifest["documents"]["outline"].update(
            {"path": str(root.parent / "outside.md")}
        ),
        lambda manifest, root: manifest["documents"]["outline"].update(
            {"path": str(root / "nested" / ".." / "outline.md")}
        ),
        lambda manifest, root: manifest["documents"]["outline"].update(
            {"contentHash": "NOT-A-SHA256"}
        ),
    ],
)
def test_pull_rejects_untrusted_manifest_document_bindings(
    tmp_path: Path,
    mutate_manifest,
) -> None:
    export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="旧大纲",
        manuscript="旧正文",
        metadata={"outlineUpdatedAt": "v1", "manuscriptUpdatedAt": "v1"},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate_manifest(manifest, tmp_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(DirtySnapshotError):
        export_snapshot(
            tmp_path,
            novel_id="novel-1",
            outline="服务端新大纲",
            manuscript="服务端新正文",
            metadata={"outlineUpdatedAt": "v2", "manuscriptUpdatedAt": "v2"},
        )

    assert (tmp_path / "outline.md").read_text(encoding="utf-8") == "旧大纲"


def test_snapshot_manifest_contains_absolute_paths_and_exact_hashes(tmp_path: Path) -> None:
    result = export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="蓝图",
        manuscript="正文😀",
        metadata={"currentOutlineVersionId": "outline-v1"},
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert Path(result["manifestPath"]).is_absolute()
    assert manifest["documents"]["manuscript"]["contentHash"] == sha256_text("正文😀")
    assert Path(manifest["documents"]["outline"]["path"]).is_absolute()


def test_eighty_thousand_character_content_and_diff_keep_the_tail(tmp_path: Path) -> None:
    content = "甲" * 80_000 + "正文尾部😀"
    diff = {"hunks": [{"old": content, "new": content + "差异尾部"}]}

    content_result = write_large_result(tmp_path / "manuscript.txt", content)
    diff_result = write_large_result(
        tmp_path / "diff.json",
        json.dumps(diff, ensure_ascii=False),
    )

    assert Path(content_result["path"]).read_text(encoding="utf-8").endswith("正文尾部😀")
    assert Path(diff_result["path"]).read_text(encoding="utf-8").endswith('差异尾部"}]}')


def test_atomic_write_never_leaves_the_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "result.txt"
    atomic_write_text(target, "完整内容")

    assert target.read_text(encoding="utf-8") == "完整内容"
    assert not list(tmp_path.glob("*.tmp"))
