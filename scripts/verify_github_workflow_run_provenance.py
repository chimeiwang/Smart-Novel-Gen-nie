#!/usr/bin/env python3
"""复验 development evidence artifact 的 GitHub Workflow run 来源。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from github_api_evidence import read_regular


class ProvenanceInvalid(ValueError):
    """GitHub Workflow run 不是获准的 development evidence producer。"""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceInvalid(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(
            read_regular(
                path,
                "Workflow run API 响应",
                error_type=ProvenanceInvalid,
            ).decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=lambda _raw: (_ for _ in ()).throw(
                ProvenanceInvalid("Workflow run API 响应禁止浮点数")
            ),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                ProvenanceInvalid(f"Workflow run API 响应包含非法数字：{raw}")
            ),
        )
    except ProvenanceInvalid:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceInvalid("Workflow run API 响应不是有效 JSON") from error
    if not isinstance(document, dict):
        raise ProvenanceInvalid("Workflow run API 响应顶层不是对象")
    return document


def verify(arguments: argparse.Namespace) -> None:
    document = _load(arguments.run_json)
    try:
        run_id = str(document["id"])
        repository = document["repository"]["full_name"]
    except (KeyError, TypeError) as error:
        raise ProvenanceInvalid("Workflow run API 响应缺少身份字段") from error
    expected = {
        "run ID": (run_id, arguments.expected_run_id),
        "workflow path": (document.get("path"), arguments.expected_workflow_path),
        "head SHA": (document.get("head_sha"), arguments.expected_head_sha),
        "head branch": (document.get("head_branch"), "main"),
        "event": (document.get("event"), "workflow_dispatch"),
        "status": (document.get("status"), "completed"),
        "conclusion": (document.get("conclusion"), "success"),
        "repository": (repository, arguments.expected_repository),
    }
    if arguments.expected_run_attempt is not None:
        expected["run attempt"] = (
            str(document.get("run_attempt")),
            arguments.expected_run_attempt,
        )
    for label, (actual, wanted) in expected.items():
        if actual != wanted:
            raise ProvenanceInvalid(f"{label} 不一致")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-workflow-path", required=True)
    parser.add_argument("--expected-run-attempt")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        verify(arguments)
    except ProvenanceInvalid as error:
        print(f"github-workflow-run-provenance:error:{error}", file=sys.stderr)
        return 1
    print(f"github-workflow-run-provenance-ok:{arguments.expected_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
