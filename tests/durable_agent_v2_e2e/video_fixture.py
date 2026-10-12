"""视频隔离替身只返回原模型阶段结构，不越过 Agent 物化或 Core 接续。"""

from __future__ import annotations

import json
from typing import cast

import httpx
import jsonschema_rs
from inkforge_agents.providers.openai_compatible import (
    _compile_responses_wire_schema,
    _schema_sha256,
)
from inkforge_agents.providers.video_responses import (
    VideoResponsesIdentity,
    VideoResponsesRequest,
    VideoResponsesResult,
    VideoResponsesUsage,
)
from inkforge_contracts.execution import canonical_execution_sha256
from inkforge_contracts.video_adaptation import SeedanceShotPromptSpec, compile_seedance_shot_prompt
from pydantic import JsonValue

SOURCE = "甲坐在书房木桌旁，抬头看向门口。"
TITLE = "隔离视频完整来源"
NAMES = {
    "chapter_dramatic_structure_v3": "dramatic_structure",
    "chapter_goal_driven_shot_design_v3": "shot_design",
    "chapter_cinematic_review_v3": "cinematic_review",
    "chapter_shot_prompt_spec_v4": "shot_prompt",
}
FAKE_IDENTITY = VideoResponsesIdentity(
    provider="fake",
    model="fake",
    transport_profile="transport.fake.v1",
    endpoint_profile="endpoint.local-fake.v1",
    capability_version="capability.fake.structured-output.v1",
    supports_request_idempotency=False,
)


def dramatic() -> dict[str, JsonValue]:
    return {
        "scenes": [
            {
                "title": "书房里的注意转移",
                "locationLabel": "书房",
                "timeLabel": "日间",
                "objective": "呈现甲注意到门口",
                "changeSummary": "甲从静坐转为注意门口",
                "beats": [
                    {
                        "title": "抬头望向门口",
                        "sourceUnitIds": ["U001"],
                        "dramaticTurn": "注意从木桌转向门口",
                        "visualStrategy": "保持一个连续反应镜头",
                        "coverageGoals": [
                            {
                                "kind": "story_information",
                                "priority": "essential",
                                "description": "观众看清甲注意到门口",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def design() -> dict[str, JsonValue]:
    return {
        "beatsByKey": {
            "B01": [
                {
                    "title": "甲抬头",
                    "narrativePurpose": "reaction",
                    "storyFunction": "呈现注意的改变",
                    "audienceGain": "观众看清甲注意到门口",
                    "coveredGoalKeys": ["G01"],
                    "sourceRelation": "direct",
                    "shotScale": "medium",
                    "cameraAngle": "eye_level",
                    "cameraMovement": "locked",
                    "visualIntent": SOURCE,
                    "speechMode": "none",
                    "spokenText": None,
                    "soundDesign": "衣料轻响，书房安静",
                    "cutReason": "视线移向门口带来新的注意方向",
                    "timelineDurationMs": 4000,
                    "sourceUnitIds": ["U001"],
                }
            ]
        },
        "suggestedEpisodeBreakAfterShotNumbers": [],
    }


def review() -> dict[str, JsonValue]:
    return {
        "decision": "pass",
        "summary": "连续反应清楚呈现注意转移",
        "requiredChanges": [],
        "findings": [],
    }


def prompt(*, correction: bool) -> dict[str, JsonValue]:
    subject = "甲坐在书房木桌旁"
    camera = "中景固定机位"
    audio = "衣料轻响，书房安静"
    gaze = None
    if not correction:
        # 各字段仍满足原动态 Schema，总编译字数超限才是本场景唯一纠正原因。
        subject += "，" + "书房木纹保持清晰，" * 18
        camera += "，" + "机位平稳保持水平，" * 14
        audio += "，" + "室内衣料轻响，" * 13
        gaze = "目光朝向门口，" * 10
    return {
        "prompts": [
            {
                "shotKey": "S01",
                "spec": {
                    "subjectAndScene": subject,
                    "visibleAction": "甲抬头看向门口",
                    "expressionAndGaze": gaze,
                    "camera": camera,
                    "audio": audio,
                    "negativeConstraints": [],
                },
            }
        ]
    }


def compiled_prompt(*, correction: bool) -> str:
    batch = cast(dict, prompt(correction=correction))
    return compile_seedance_shot_prompt(
        SeedanceShotPromptSpec.model_validate(batch["prompts"][0]["spec"]),
        ratio="16:9",
        timeline_duration_ms=4000,
    )


def request_identity(request: VideoResponsesRequest) -> dict[str, str]:
    digest = canonical_execution_sha256(request.model_dump(mode="json"))
    # 仅用于测试侧统计相同内容的真实调用次数，不向供应商声明幂等保证。
    return {"idempotencyKey": "video." + digest, "requestSha256": digest}


def video_result(request: VideoResponsesRequest) -> VideoResponsesResult:
    stage = NAMES.get(request.structuredOutput.name)
    if stage is None or [message.role for message in request.messages] != ["system", "user"]:
        raise ValueError("视频隔离测试收到未声明阶段或非原消息形状")
    content = request.messages[1].content
    if stage != "shot_prompt" and SOURCE not in content:
        raise ValueError("视频隔离阶段丢失完整冻结原文")
    if stage == "dramatic_structure":
        output = dramatic()
        if request.structuredOutput.jsonSchema["$defs"]["DramaticBeatDraft"]["properties"][
            "sourceUnitIds"
        ]["items"]["enum"] != ["U001"]:
            raise ValueError("戏剧分析动态来源 Schema 没有绑定完整原文单元")
    elif stage == "shot_design":
        output = design()
        if '"beatKey":"B01"' not in content or '"goalKey":"G01"' not in content:
            raise ValueError("镜头设计没有使用 Core 保存的完整检查点")
    elif stage == "cinematic_review":
        output = review()
        if '"shotKey":"S01"' not in content or "确定性提示 JSON" not in content:
            raise ValueError("审镜未读取完整候选和原确定性发现")
    else:
        correction = content.startswith("上一次响应没有形成可执行的逐镜规格。")
        if correction:
            expected = (
                f"S01 编译后 {len(compiled_prompt(correction=False))} 字，超过当前时长的 480 字上限"
            )
            issues = json.loads(content.split("必须修正的问题 JSON：", 1)[1].split("\n", 1)[0])
            if issues != [expected]:
                raise ValueError("提示词纠正没有传入原具体编译预算原因")
        output = prompt(correction=correction)
    jsonschema_rs.validator_for(request.structuredOutput.jsonSchema).validate(output)
    prompt_tokens = sum(len(message.content) for message in request.messages)
    completion_tokens = len(json.dumps(output, ensure_ascii=False))
    return VideoResponsesResult(
        structuredOutput=output,
        diagnostic=None,
        finishReason="stop",
        rawFinishReason="response.completed",
        providerResponseId="e2e-video-" + request_identity(request)["requestSha256"][:32],
        usage=VideoResponsesUsage(
            inputTokens=prompt_tokens,
            cachedTokens=0,
            promptCacheMissTokens=prompt_tokens,
            completionTokens=completion_tokens,
            reasoningTokens=0,
            visibleOutputTokens=completion_tokens,
            totalTokens=prompt_tokens + completion_tokens,
            costMicros=0,
        ),
        localSchemaSha256=_schema_sha256(request.structuredOutput.jsonSchema),
        wireSchemaSha256=_schema_sha256(_compile_responses_wire_schema(request.structuredOutput)),
    )


class ControlledVideoResponsesProvider:
    identity = FAKE_IDENTITY

    def __init__(self, *, control_url: str, control_token: str) -> None:
        self._control_url = control_url
        self._control_token = control_token

    async def complete_responses(self, request: VideoResponsesRequest) -> VideoResponsesResult:
        identity = request_identity(request)
        async with httpx.AsyncClient(
            base_url=self._control_url,
            timeout=120.0,
            trust_env=False,
            headers={"X-InkForge-E2E-Token": self._control_token},
        ) as http:
            response = await http.post("/control/provider/reached", json=identity)
            response.raise_for_status()
            result = video_result(request)
            response = await http.post("/control/provider/completed", json=identity)
            response.raise_for_status()
            return result
