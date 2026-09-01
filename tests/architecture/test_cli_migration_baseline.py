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
V2_CONTRACT_ERROR_PARITY = (
    ROOT / "contracts" / "cli" / "parity-v2-contract-error-cases.json"
)


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

    answer = next(case for case in cases if case["command"] == "long.agent.start")
    assert answer["payload"]["operation"] == "answer_question"
    assert answer["payload"]["writingSessionId"] == "s1"
    assert answer["payload"]["target"] == {"type": "chapter", "id": "c1"}
    assert answer["payload"]["scope"] == {"kind": "chapter", "chapterId": "c1"}


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
    assert len(cases) == 7
    assert {case["command"] for case in cases} == expected
    assert all(case.get("fakeClock") is True for case in cases)
    assert all(isinstance(case.get("responses"), list) for case in cases)

    long_watch = next(
        case
        for case in cases
        if case["command"] == "long.task.watch" and "caseId" not in case
    )
    assert all(response["engineVersion"] == 2 for response in long_watch["responses"])
    assert all("outcome" not in response for response in long_watch["responses"])
    assert [response["status"] for response in long_watch["responses"]] == [
        "running",
        "running",
        "completed",
    ]
    assert long_watch["streams"][0][0]["event"] == "run_snapshot"
    assert type(long_watch["streams"][0][0]["id"]) is int

    waiting = next(
        case
        for case in cases
        if case.get("caseId") == "long-v2-waiting-artifact-object"
    )["responses"][0]
    failed = next(
        case
        for case in cases
        if case.get("caseId") == "long-v2-failed-error-object"
    )["responses"][0]
    assert isinstance(waiting["activeSteps"], list)
    assert isinstance(waiting["artifact"], dict)
    assert waiting["error"] is None
    assert isinstance(failed["activeSteps"], list)
    assert failed["artifact"] is None
    assert isinstance(failed["error"], dict)


def test_cli_v2_contract_error_fixture_closes_cross_language_gaps() -> None:
    registry = json.loads(BASELINE.read_text(encoding="utf-8"))
    registered = {command["name"] for command in registry["commands"]}
    fixture = json.loads(V2_CONTRACT_ERROR_PARITY.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    by_id = {case["caseId"]: case for case in cases}

    assert (
        fixture["schemaVersion"]
        == "inkforge-cli-parity-v2-contract-errors/1.0"
    )
    assert len(cases) == 16
    assert len(by_id) == len(cases)
    assert all(case["mode"] == "scripted" for case in cases)
    assert all(case["captureCalls"] is True for case in cases)
    assert {case["command"] for case in cases} <= registered

    answer_ids = {
        "answer-session-missing",
        "answer-session-null",
        "answer-session-empty",
        "answer-session-number",
        "answer-target-wrong-chapter",
        "answer-scope-wrong-chapter",
        "answer-operation-unsupported",
        "answer-top-level-unexpected-field",
        "answer-instruction-unicode-blank",
    }
    answer_cases = [by_id[case_id] for case_id in sorted(answer_ids)]
    assert all(case["command"] == "long.agent.start" for case in answer_cases)
    assert all(case["expectedExitCode"] == 2 for case in answer_cases)
    assert all(case["expectedCalls"] == [] for case in answer_cases)
    assert {
        case["caseId"]: case["expectedErrorCode"] for case in answer_cases
    } == {
        "answer-session-missing": "WRITING_SESSION_REQUIRED",
        "answer-session-null": "WRITING_SESSION_REQUIRED",
        "answer-session-empty": "WRITING_SESSION_REQUIRED",
        "answer-session-number": "WRITING_SESSION_REQUIRED",
        "answer-target-wrong-chapter": "INVALID_TARGET",
        "answer-scope-wrong-chapter": "INVALID_SCOPE",
        "answer-operation-unsupported": "INVALID_OPERATION",
        "answer-top-level-unexpected-field": "UNEXPECTED_FIELD",
        "answer-instruction-unicode-blank": "INVALID_USER_INSTRUCTION",
    }
    assert "writingSessionId" not in by_id["answer-session-missing"]["payload"]
    assert by_id["answer-session-null"]["payload"]["writingSessionId"] is None
    assert by_id["answer-session-empty"]["payload"]["writingSessionId"] == ""
    assert type(
        by_id["answer-session-number"]["payload"]["writingSessionId"]
    ) is int
    assert (
        by_id["answer-target-wrong-chapter"]["payload"]["target"]["id"]
        != by_id["answer-target-wrong-chapter"]["payload"]["chapterId"]
    )
    assert (
        by_id["answer-scope-wrong-chapter"]["payload"]["scope"]["chapterId"]
        != by_id["answer-scope-wrong-chapter"]["payload"]["chapterId"]
    )
    assert not by_id["answer-instruction-unicode-blank"]["payload"][
        "userInstruction"
    ].strip()
    assert (
        by_id["answer-operation-unsupported"]["payload"]["operation"]
        not in {
            "answer_question",
            "plan_chapter",
            "write_chapter",
            "review_chapter",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
        }
    )
    assert set(by_id["answer-top-level-unexpected-field"]["payload"]) - {
        "clientRequestId",
        "novelId",
        "chapterId",
        "operation",
        "target",
        "scope",
        "writingSessionId",
        "userInstruction",
    } == {"selectedAgents"}

    watcher_cases = [
        case for case in cases if case["command"] == "long.task.watch"
    ]
    watcher_ids = {
        "watch-active-steps-missing",
        "watch-active-steps-null",
        "watch-active-steps-object",
        "watch-artifact-array",
        "watch-artifact-string",
        "watch-error-array",
        "watch-error-string",
    }
    expected_get: list[dict[str, object]] = [
        {
            "kind": "request",
            "method": "GET",
            "path": "/api/v1/writing/runs/t%2F1",
            "query": {},
            "body": None,
        }
    ]
    assert len(watcher_cases) == 7
    assert {case["caseId"] for case in watcher_cases} == watcher_ids
    assert all(case["fakeClock"] is True for case in watcher_cases)
    assert all(case["expectedExitCode"] == 5 for case in watcher_cases)
    assert all(
        case["expectedErrorCode"] == "CORE_RESPONSE_CONTRACT_ERROR"
        for case in watcher_cases
    )
    assert all(case["expectedCalls"] == expected_get for case in watcher_cases)


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
