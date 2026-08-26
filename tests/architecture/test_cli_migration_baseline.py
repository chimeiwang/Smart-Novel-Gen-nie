from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "contracts" / "cli" / "command-registry.json"
SUCCESS_PARITY = ROOT / "contracts" / "cli" / "parity-success-cases.json"
WATCH_PARITY = ROOT / "contracts" / "cli" / "parity-watch-cases.json"
FILE_PARITY = ROOT / "contracts" / "cli" / "parity-file-cases.json"


def test_cli_command_registry_baseline_is_complete() -> None:
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    commands = document["commands"]
    names = [command["name"] for command in commands]

    assert document["schemaVersion"] == "inkforge-cli-command-registry/1.0"
    assert len(commands) == 125
    assert len(names) == len(set(names))
    assert names[0] == "auth.login"
    assert names[-1] == "long.video.export.download"
    assert sum(command["outputMode"] == "jsonl" for command in commands) == 5
    assert sum(
        command["name"].startswith("long.") and command["mutation"]
        for command in commands
    ) == 74
    assert all("/internal/" not in command["name"] for command in commands)


def test_cli_command_registry_export_has_no_drift() -> None:
    result = subprocess.run(  # noqa: S603 -- 只执行当前解释器与仓库内固定脚本
        [
            sys.executable,
            str(ROOT / "scripts" / "export_cli_migration_baseline.py"),
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_success_parity_fixture_is_language_neutral_and_registered() -> None:
    registry = json.loads(BASELINE.read_text(encoding="utf-8"))
    fixture = json.loads(SUCCESS_PARITY.read_text(encoding="utf-8"))
    registered = {command["name"] for command in registry["commands"]}
    cases = fixture["cases"]
    names = [case["command"] for case in cases]

    assert fixture["schemaVersion"] == "inkforge-cli-parity-success/1.0"
    assert len(cases) == 30
    assert len(names) == len(set(names))
    assert set(names) <= registered
    assert {name.split(".", 1)[0] for name in names} == {"auth", "short", "long"}
    assert any(name.startswith("long.video.") for name in names)
    assert all(isinstance(case.get("payload", {}), dict) for case in cases)


def test_cli_watch_parity_fixture_covers_every_jsonl_command() -> None:
    registry = json.loads(BASELINE.read_text(encoding="utf-8"))
    fixture = json.loads(WATCH_PARITY.read_text(encoding="utf-8"))
    expected = {
        command["name"]
        for command in registry["commands"]
        if command["outputMode"] == "jsonl"
    }
    cases = fixture["cases"]

    assert fixture["schemaVersion"] == "inkforge-cli-parity-watch/1.0"
    assert {case["command"] for case in cases} == expected
    assert all(case.get("fakeClock") is True for case in cases)
    assert all(isinstance(case.get("responses"), list) for case in cases)


def test_cli_file_parity_fixture_covers_text_json_upload_and_download_bytes() -> None:
    registry = json.loads(BASELINE.read_text(encoding="utf-8"))
    fixture = json.loads(FILE_PARITY.read_text(encoding="utf-8"))
    registered = {command["name"] for command in registry["commands"]}
    cases = fixture["cases"]
    names = [case["command"] for case in cases]

    assert fixture["schemaVersion"] == "inkforge-cli-parity-file/1.0"
    assert len(cases) == 10
    assert len(names) == len(set(names))
    assert set(names) <= registered
    assert sum("files" in case for case in cases) == 3
    assert sum("captureFiles" in case for case in cases) == 7
    assert {
        "long.video.asset.upload",
        "long.video.asset.download",
        "long.video.take.download",
        "long.video.export.download",
    } <= set(names)

    for case in cases:
        assert isinstance(case.get("payload", {}), dict)
        for specification in case.get("files", {}).values():
            assert specification["encoding"] in {"utf8", "base64"}
            assert isinstance(specification["content"], str)
            if specification["encoding"] == "base64":
                base64.b64decode(specification["content"], validate=True)
        for name in case.get("captureFiles", []):
            assert isinstance(name, str) and name
