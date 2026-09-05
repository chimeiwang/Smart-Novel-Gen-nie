from __future__ import annotations

import json
import subprocess  # noqa: S404 -- 仅运行仓库内固定导出脚本
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "contracts" / "core" / "agent"

AGENT_UPDATES_SCHEMA_PATHS = {
    f"agent_updates/{model}.schema.json"
    for model in (
        "AgentUpdates",
        "AgentUpdatesInput",
        "AgentUpdatesEvidenceNeed",
        "AgentUpdatesEvidenceRequestOutput",
        "AgentUpdatesOutput",
        "AgentUpdatesPreviousCandidate",
        "AgentUpdatesResult",
        "CharacterCreate",
        "CharacterDelete",
        "CharacterExperienceCreate",
        "CharacterExperienceDelete",
        "CharacterExperienceUpdate",
        "CharacterUpdate",
        "FactionCreate",
        "FactionDelete",
        "FactionUpdate",
        "ForeshadowingAbandon",
        "ForeshadowingCreate",
        "ForeshadowingPayoff",
        "ForeshadowingUpdate",
        "GlossaryCreate",
        "GlossaryDelete",
        "GlossaryUpdate",
        "ItemCreate",
        "ItemDelete",
        "ItemUpdate",
        "LocationCreate",
        "LocationDelete",
        "LocationUpdate",
        "OutlineAdjustmentCreate",
        "OutlineAdjustmentDelete",
        "OutlineAdjustmentUpdate",
        "OutlineUpdate",
        "ReferenceCreate",
        "ReferenceDelete",
        "ReferenceUpdate",
    )
}


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
        "agent_updates/AgentUpdates.schema.json",
        "agent_updates/AgentUpdatesInput.schema.json",
        "agent_updates/AgentUpdatesOutput.schema.json",
        "agent_updates/AgentUpdatesResult.schema.json",
        "events/RunCompletionCallback.schema.json",
        "execution/BillingReconciliationReceipt.schema.json",
        "execution/BillingReconciliationRequest.schema.json",
        "execution/ExecutionCancelRequest.schema.json",
        "execution/ExecutionStepFailure.schema.json",
        "execution/ExecutionStepRequest.schema.json",
        "execution/ExecutionStepResult.schema.json",
        "execution/IntentAvailableOperationV2.schema.json",
        "execution/IntentContextV2.schema.json",
        "execution/PromptProfileRef.schema.json",
        "jobs/AgentJobRequest.schema.json",
        "jwt_claims/ServiceJwtClaims.schema.json",
        "quality/ConsistencyQualityReport.schema.json",
        "video_adaptation/ChapterAdaptationPlanJobPayload.schema.json",
        "video_render/SeedanceRenderSubmitRequest.schema.json",
    } <= paths
    assert {path for path in paths if path.startswith("agent_updates/")} == (
        AGENT_UPDATES_SCHEMA_PATHS
    )
    assert not any(path.startswith("agent_updates/_") for path in paths)
    agent_updates_schema = json.loads(
        (generated / "agent_updates" / "AgentUpdates.schema.json").read_text()
    )
    assert [
        branch["$ref"]
        for branch in agent_updates_schema["$defs"]["CharacterMutation"]["anyOf"]
    ] == [
        "#/$defs/CharacterCreate",
        "#/$defs/CharacterUpdate",
        "#/$defs/CharacterDelete",
    ]
    assert [
        branch["$ref"]
        for branch in agent_updates_schema["$defs"]["OutlineAdjustment"]["anyOf"]
    ] == [
        "#/$defs/OutlineAdjustmentCreate",
        "#/$defs/OutlineAdjustmentUpdate",
        "#/$defs/OutlineAdjustmentDelete",
    ]
    for item in actual_manifest["models"]:
        relative_path = item["path"]
        assert (generated / relative_path).read_bytes() == (BASELINE / relative_path).read_bytes()
