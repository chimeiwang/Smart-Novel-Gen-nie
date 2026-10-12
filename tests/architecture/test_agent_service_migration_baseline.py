from __future__ import annotations

import json
import subprocess  # noqa: S404 -- 仅执行仓库内固定导出脚本
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "agent-service"


def _operation_count(document: dict[str, object]) -> int:
    methods = {"get", "post", "put", "patch", "delete"}
    return sum(
        method in methods
        for path_item in document["paths"].values()  # type: ignore[union-attr]
        for method in path_item
    )


def test_agent_service_openapi_covers_core_outbound_calls() -> None:
    source = json.loads((CONTRACT_ROOT / "openapi-python-baseline.json").read_text())
    java = json.loads((CONTRACT_ROOT / "openapi-java-baseline.json").read_text())

    assert len(source["paths"]) == 10
    assert _operation_count(source) == 10
    assert len(source["components"]["schemas"]) == 27
    assert source["paths"].keys() == java["paths"].keys()
    assert java["openapi"] == "3.0.3"
    assert {
        "AgentJobRequest",
        "AgentJobAccepted",
        "AgentJobCancelRequest",
        "ExecutionStepRequest",
        "ExecutionStepAccepted",
        "ExecutionCancelRequest",
        "ExecutionCancelAccepted",
        "ResolvedModelRef",
        "EvidenceBundle",
        "OutputSchemaRef",
        "PromptProfileRef",
        "StepBudget",
        "SeedanceRenderSubmitRequest",
        "SeedanceRenderQueryResponse",
    } <= source["components"]["schemas"].keys()


def test_agent_service_openapi_export_has_no_drift() -> None:
    result = subprocess.run(  # noqa: S603 -- 解释器与脚本路径固定
        [
            sys.executable,
            str(ROOT / "scripts" / "export_agent_service_migration_baseline.py"),
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
