from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from inkforge_cli.json_types import JsonObject
from inkforge_cli.registry import CommandSpec, FileOutputSpec
from inkforge_cli.runtime import (
    CoreResponseContractError,
    LocalFileError,
    emit_command_result,
)


def _unused_handler(runtime: object, payload: JsonObject) -> JsonObject:
    return payload


def _spec(file_output: FileOutputSpec) -> CommandSpec:
    return CommandSpec(
        name="long.test",
        handler=_unused_handler,
        inputMode="json",
        outputMode="json",
        fileOutput=file_output,
        mutation=False,
        requiresIdentity=False,
        requiresClientRequestId=False,
    )


def test_data_json_writes_complete_unwrapped_data_and_returns_descriptor(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "result.json"
    stdout = io.StringIO()
    data: JsonObject = {"content": "正文尾部😀", "sequence": 7}

    code = emit_command_result(
        _spec(FileOutputSpec(kind="data_json")),
        data,
        stdout,
        payload={"outputFile": str(output_file)},
    )

    expected_bytes = (
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    descriptor = json.loads(stdout.getvalue())["data"]["resultFile"]
    assert code == 0
    assert output_file.read_bytes() == expected_bytes
    assert descriptor == {
        "path": str(output_file.resolve()),
        "bytes": len(expected_bytes),
        "sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "mediaType": "application/json; charset=utf-8",
    }


def test_primary_text_replaces_only_the_declared_field(tmp_path: Path) -> None:
    output_file = tmp_path / "chapter.txt"
    stdout = io.StringIO()

    emit_command_result(
        _spec(
            FileOutputSpec(
                kind="primary_text",
                field="content",
                media_type="text/plain; charset=utf-8",
            )
        ),
        {"id": "chapter-1", "content": "第一行\r\n正文尾部😀"},
        stdout,
        payload={"outputFile": str(output_file)},
    )

    data = json.loads(stdout.getvalue())["data"]
    assert output_file.read_bytes() == "第一行\r\n正文尾部😀".encode()
    assert data["id"] == "chapter-1"
    assert "content" not in data
    assert data["contentFile"]["path"] == str(output_file.resolve())


def test_file_output_is_never_selected_implicitly(tmp_path: Path) -> None:
    stdout = io.StringIO()
    data: JsonObject = {"content": "完整正文"}

    emit_command_result(
        _spec(FileOutputSpec(kind="data_json")),
        data,
        stdout,
        payload={},
    )

    assert json.loads(stdout.getvalue())["data"] == data
    assert list(tmp_path.iterdir()) == []


def test_primary_text_requires_the_declared_response_field(tmp_path: Path) -> None:
    with pytest.raises(CoreResponseContractError):
        emit_command_result(
            _spec(
                FileOutputSpec(
                    kind="primary_text",
                    field="content",
                    media_type="text/plain; charset=utf-8",
                )
            ),
            {"id": "chapter-1"},
            io.StringIO(),
            payload={"outputFile": str(tmp_path / "chapter.txt")},
        )


def test_output_write_error_is_wrapped_as_a_local_file_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_write(output_file: str, payload: bytes, media_type: str) -> object:
        raise PermissionError("拒绝写入")

    monkeypatch.setattr("inkforge_cli.runtime.write_bytes", fail_write)

    with pytest.raises(LocalFileError):
        emit_command_result(
            _spec(FileOutputSpec(kind="data_json")),
            {"value": 1},
            io.StringIO(),
            payload={"outputFile": str(tmp_path / "result.json")},
        )
