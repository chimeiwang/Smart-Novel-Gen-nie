from __future__ import annotations

import json
import subprocess  # noqa: S404 -- 仅运行仓库内固定导出脚本
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "contracts" / "core" / "agent"


def test_agent_contract_schema_baseline_is_complete_and_reproducible(tmp_path: Path) -> None:
    generated = tmp_path / "agent-contracts"
    subprocess.run(  # noqa: S603 -- 解释器与脚本路径均由测试固定
        [
            sys.executable,
            str(ROOT / "scripts" / "export_agent_contract_schemas.py"),
            "--output",
            str(generated),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    expected_manifest = json.loads((BASELINE / "manifest.json").read_text())
    actual_manifest = json.loads((generated / "manifest.json").read_text())
    assert actual_manifest == expected_manifest
    assert actual_manifest["modelCount"] >= 150

    paths = {item["path"] for item in actual_manifest["models"]}
    assert {
        "events/RunCompletionCallback.schema.json",
        "jobs/AgentJobRequest.schema.json",
        "jwt_claims/ServiceJwtClaims.schema.json",
        "quality/ConsistencyQualityReport.schema.json",
        "video_adaptation/ChapterAdaptationPlanJobPayload.schema.json",
        "video_render/SeedanceRenderSubmitRequest.schema.json",
    } <= paths
    for item in actual_manifest["models"]:
        relative_path = item["path"]
        assert (generated / relative_path).read_bytes() == (BASELINE / relative_path).read_bytes()
