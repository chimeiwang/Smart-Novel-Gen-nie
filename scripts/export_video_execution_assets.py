#!/usr/bin/env python3
"""从原视频静态提示与共享阶段结果生成视频专用资产，不修改其他操作声明。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from inkforge_agents.jobs import video_adaptation as original
from inkforge_contracts.execution import canonical_execution_sha256
from inkforge_contracts.video_execution import (
    VideoCinematicReviewOutput,
    VideoDramaticStructureOutput,
    VideoMissingBeatShotsOutput,
    VideoShotDesignOutput,
    VideoShotPromptOutput,
)
from refresh_agent_execution_manifest import model_output_schema

ROOT = Path(__file__).resolve().parents[1] / "contracts" / "agent-execution"
STAGES = (
    (
        "dramatic_structure",
        VideoDramaticStructureOutput,
        original._dramatic_system_prompt,
        48_000,
        1_500_000,
        2,
    ),
    (
        "shot_design",
        VideoShotDesignOutput,
        original._shot_design_system_prompt,
        48_000,
        1_500_000,
        3,
    ),
    (
        "missing_beat_shots",
        VideoMissingBeatShotsOutput,
        original._shot_design_system_prompt,
        16_000,
        1_000_000,
        3,
    ),
    (
        "cinematic_review",
        VideoCinematicReviewOutput,
        original._review_system_prompt,
        12_000,
        1_000_000,
        2,
    ),
    ("shot_prompt", VideoShotPromptOutput, original._prompt_system_prompt, 48_000, 1_500_000, 2),
)


def upsert(filename: str, array: str, value: dict[str, object]) -> None:
    """只替换精确具名条目，保留其他资产原字节和格式。"""
    path = ROOT / filename
    raw = path.read_text()
    encoded = json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n    ")
    match = re.search(r'"key"\s*:\s*' + re.escape(json.dumps(value["key"])), raw)
    if match:
        start = raw.rfind("{", 0, match.start())
        _, length = json.JSONDecoder().raw_decode(raw[start:])
        raw = raw[:start] + encoded + raw[start + length :]
    else:
        match = re.search(json.dumps(array) + r"\s*:\s*\[", raw)
        if match is None:
            raise ValueError("资产数组缺失")
        raw = raw[: match.end()] + "\n    " + encoded + "," + raw[match.end() :]
    json.loads(raw)
    path.write_text(raw)


def main() -> None:
    for stage, output_type, prompt_function, output_limit, cost, _ in STAGES:
        deployment = (
            "deployment.video.shot_prompt.v2"
            if stage == "shot_prompt"
            else "deployment.video.chapter_adaptation.v2"
        )
        prompt = prompt_function()
        upsert(
            "profile-registry.v1.json",
            "profiles",
            {
                "key": f"video.{stage}.v2",
                "version": 2,
                "supported": True,
                "reasoningMode": "disabled",
                "purpose": "generation",
                "promptProfile": f"prompt.video.{stage}.v2",
                "deploymentProfileKey": deployment,
            },
        )
        upsert(
            "prompt-profile-registry.v1.json",
            "prompts",
            {
                "key": f"prompt.video.{stage}.v2",
                "version": 2,
                "supported": True,
                "purpose": "generation",
                "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "systemPrompt": prompt,
            },
        )
        schema = model_output_schema(output_type)
        upsert(
            "output-schema-registry.v1.json",
            "schemas",
            {
                "key": f"output.video_{stage}_stage.v2",
                "version": 2,
                "supported": True,
                "purpose": "generation",
                "sha256": canonical_execution_sha256(schema),
                "jsonSchema": schema,
            },
        )
        upsert(
            "step-budget-registry.v1.json",
            "budgets",
            {
                "key": f"step_budget.video.{stage}.v2",
                "version": 2,
                "supported": True,
                "budget": {
                    "maxModelCalls": 1,
                    "maxInputTokens": 240_000,
                    "maxPromptCacheMissTokens": 240_000,
                    "maxCompletionTokens": output_limit,
                    "maxReasoningTokens": 0,
                    "maxVisibleOutputTokens": output_limit,
                    "maxCostMicros": cost,
                    "maxWallClockSeconds": 300,
                    "maxProviderRetries": 2,
                    "maxProtocolCorrections": 1,
                },
            },
        )
    for deployment in ("deployment.video.chapter_adaptation.v2", "deployment.video.shot_prompt.v2"):
        upsert(
            "deployment-profile-registry.v1.json",
            "profiles",
            {
                "key": deployment,
                "version": 2,
                "supported": True,
                "purpose": "generation",
                "allowedModels": [
                    {
                        "provider": "openai_compatible",
                        "model": "deepseek-v4-flash",
                        "transportProfile": "transport.deepseek-responses.v1",
                        "endpointProfile": "endpoint.deepseek-responses-official.v1",
                        "structuredOutputRoute": "responses_json_schema_v1",
                        "capabilityVersion": "capability.deepseek-responses.json-schema.v1",
                        "reasoningMode": "disabled",
                        "supportsRequestIdempotency": False,
                        "allowedEnvironments": ["dev", "test"],
                        "pricingVersion": "credit-pricing.v1",
                        "billable": True,
                    },
                    {
                        "provider": "fake",
                        "model": "fake",
                        "transportProfile": "transport.fake.v1",
                        "endpointProfile": "endpoint.local-fake.v1",
                        "structuredOutputRoute": "responses_json_schema_v1",
                        "capabilityVersion": "capability.fake.structured-output.v1",
                        "reasoningMode": "disabled",
                        "supportsRequestIdempotency": False,
                        "allowedEnvironments": ["test"],
                        "pricingVersion": "credit-pricing.v1",
                        "billable": False,
                    },
                ],
            },
        )
    catalog = json.loads((ROOT / "operation-catalog.v1.json").read_text())
    for operation in catalog["operations"]:
        if operation["key"] not in {
            "video.chapter_cinematic_adaptation_v2",
            "video.chapter_shot_prompt_v2",
        }:
            continue
        prompt = operation["operation"] == "chapter_shot_prompt_v2"
        stages = STAGES[-1:] if prompt else STAGES[:4]
        operation.update(
            generatorProfile=f"video.{stages[0][0]}.v2",
            outputSchema=f"output.video_{stages[0][0]}_stage.v2",
            generatorStepBudgetProfile=f"step_budget.video.{stages[0][0]}.v2",
            videoStagePolicy="video.shot-prompt-stages.v1"
            if prompt
            else "video.cinematic-stages.v1",
            stageSteps=[
                {
                    "stageKey": stage,
                    "modelProfile": f"video.{stage}.v2",
                    "outputSchema": f"output.video_{stage}_stage.v2",
                    "stepBudgetProfile": f"step_budget.video.{stage}.v2",
                    "maxInvocations": count,
                }
                for stage, _, _, _, _, count in stages
            ],
            reviewPolicy={
                "profile": "review.none.v1",
                "mode": "none",
                "reviewerProfiles": [],
                "mergePolicy": "review.merge_none.v1",
                "maxAutomaticRevisions": 0,
                "onUnavailable": "continue",
            },
        )
        operation["runBudgetProfile"].update(
            maxModelCalls=2 if prompt else 10,
            maxInputTokens=480_000 if prompt else 2_400_000,
            maxPromptCacheMissTokens=480_000 if prompt else 2_400_000,
            maxCompletionTokens=96_000 if prompt else 312_000,
            maxReasoningTokens=0,
            maxVisibleOutputTokens=96_000 if prompt else 312_000,
            maxCostMicros=3_000_000 if prompt else 13_000_000,
            maxWallClockSeconds=600 if prompt else 3000,
            maxProtocolCorrectionSteps=0,
            maxProviderRetriesPerStep=2,
        )
        upsert("operation-catalog.v1.json", "operations", operation)


if __name__ == "__main__":
    main()
