"""视频阶段只处理本次冻结输入，补槽、纠正与领域审镜不形成内部模型循环。"""

import asyncio
import hashlib
from dataclasses import replace
from types import MappingProxyType

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.video import (
    VideoStageOutputError,
    _prompt_finding,
    build_video_request,
    materialize_video_output,
)
from inkforge_agents.jobs import video_adaptation as original
from inkforge_agents.providers.base import ModelStructuredOutputDiagnostic, ProviderTransportError
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.providers.video_responses import (
    VideoResponsesIdentity,
    VideoResponsesResult,
    VideoResponsesUsage,
)
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_contracts.execution import (
    EvidenceManifest,
    EvidenceManifestItem,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)
from inkforge_contracts.video import LongSerialSettingSnapshot
from inkforge_contracts.video_adaptation import ChapterAdaptationPlanJobPayload
from inkforge_contracts.video_execution import (
    VideoShotDesignInput,
    VideoTaskContextV2,
    video_finding_message,
)

from .support import execution_request, rehash_request

SOURCE = "林岚推门。男人交出钥匙。"


def video_request(stage="dramatic_structure", **extra):
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="雨夜",
        sourceText=SOURCE,
        sourceHash=hashlib.sha256(SOURCE.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    context = VideoTaskContextV2(taskId="task-1", payload=payload, inheritedCheckpoint=None)
    base = execution_request()
    item = base.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": "video_task_context",
            "resourceId": "task-1",
            "contentType": "json",
            "contentText": None,
            "contentJson": context.model_dump(mode="json"),
            "range": None,
        }
    )
    data = {
        "stageKey": stage,
        "cycle": 0,
        "correction": False,
        "dependencies": []
        if stage == "dramatic_structure"
        else [{"stepId": "previous", "resultHash": "a" * 64}],
        **extra,
    }
    if stage in {"dramatic_structure", "shot_design", "shot_prompt"}:
        data.setdefault("correctionFindings", [])
    if stage == "shot_design":
        data.setdefault("requiredChanges", [])
    return base.model_copy(
        update={
            "workflow": "video",
            "operation": "chapter_cinematic_adaptation_v2",
            "purpose": "generation",
            "lane": "batch_media",
            "input": data,
            "modelProfile": base.modelProfile.model_copy(
                update={"profile": f"video.{stage}.v2", "version": 2}
            ),
            "outputSchema": base.outputSchema.model_copy(
                update={"name": f"output.video_{stage}_stage.v2", "version": 2}
            ),
            "evidenceBundle": base.evidenceBundle.model_copy(
                update={"policyVersion": "evidence.video.chapter_adaptation.v2", "items": [item]}
            ),
        }
    )


def dramatic_result():
    return {
        "scenes": [
            {
                "title": "雨夜书房",
                "locationLabel": "书房",
                "timeLabel": "雨夜",
                "objective": "确认来意",
                "changeSummary": "来客交出钥匙",
                "beats": [
                    {
                        "title": "见面",
                        "sourceUnitIds": ["U001", "U002"],
                        "dramaticTurn": "等待变为交接",
                        "visualStrategy": "跟随人物",
                        "coverageGoals": [
                            {
                                "kind": "story_information",
                                "priority": "essential",
                                "description": "交出钥匙",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def checkpoint():
    return materialize_video_output(video_request(), dramatic_result())["checkpoint"]


def test_dramatic_request_keeps_original_system_schema_and_full_units():
    request = build_video_request(video_request(), original._dramatic_system_prompt())
    assert request.messages[0].content == original._dramatic_system_prompt()
    assert request.tools == []
    assert request.structuredOutput.route == "responses_json_schema_v1"
    assert request.structuredOutput.name == "chapter_dramatic_structure_v3"
    assert request.structuredOutput.jsonSchema["$defs"]["DramaticBeatDraft"]["properties"][
        "sourceUnitIds"
    ]["items"]["enum"] == ["U001", "U002"]
    assert "林岚推门。" in request.messages[1].content
    assert "男人交出钥匙。" in request.messages[1].content


def test_dramatic_materialization_does_not_hide_correction_call():
    raw = dramatic_result()
    raw["scenes"][0]["locationLabel"] = "书房与街道"
    output = materialize_video_output(video_request(), raw)
    assert output["outcome"] == "needs_correction"
    assert output["checkpoint"] is None
    assert "书房与街道" not in str(output)


def test_incomplete_design_returns_only_frozen_supplement_facts():
    output = materialize_video_output(
        video_request("shot_design", checkpoint=checkpoint()),
        {"beatsByKey": {}, "suggestedEpisodeBreakAfterShotNumbers": []},
    )
    assert output["outcome"] == "needs_supplement"
    assert output["missingBeatKeys"] == ["B01"]
    assert output["candidate"] is None
    assert output["design"]["beatsByKey"] == {}


def test_supplement_wrong_shape_is_terminal_not_design_correction():
    request = video_request(
        "missing_beat_shots",
        checkpoint=checkpoint(),
        design={"beatsByKey": {}, "suggestedEpisodeBreakAfterShotNumbers": []},
        missingBeatKeys=["B01"],
    )
    wire = build_video_request(request, original._shot_design_system_prompt())
    assert wire.structuredOutput.name == "chapter_missing_beat_shots_v3"
    assert wire.structuredOutput.jsonSchema["properties"]["beatsByKey"]["required"] == ["B01"]
    with pytest.raises(VideoStageOutputError, match="SUPPLEMENT_INVALID"):
        materialize_video_output(request, {"beatsByKey": {}})


@pytest.mark.parametrize(
    ("text", "blocking"),
    [
        ("编译后 500 字，超过当前时长的 360 字上限", True),
        ("2.5 秒镜头最多允许 1 个动作句，当前为 3 个", False),
        ("显式景别必须保持正式近景，不能写成：特写", False),
        ("候选新增了正式镜头未确认的视觉效果：火花、血迹", False),
        ("negativeConstraints 混入了正向画面要求：火花", False),
        ("visibleAction 新增了正式镜头未确认的状态变化：凝成, 回拧", False),
        ("subjectAndScene/camera 重复了同一段镜头事实", False),
    ],
)
def test_prompt_safe_findings_exactly_round_trip_original_reasons(text, blocking):
    issue = original._PromptCandidateIssue(shot_key="S01", message=text, blocking=blocking)
    assert video_finding_message(_prompt_finding(issue)) == issue.correction_reason


def test_unknown_diagnostic_cannot_be_saved_as_arbitrary_text():
    issue = original._PromptCandidateIssue(shot_key="S01", message="供应商秘密正文", blocking=True)
    with pytest.raises(VideoStageOutputError, match="DIAGNOSTIC_INVALID"):
        _prompt_finding(issue)


def video_registry(enabled=True):
    registry = load_execution_registry(environment="test")
    return replace(
        registry,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=enabled)
                if key.startswith("video.chapter_")
                else value
                for key, value in registry.operations.items()
            }
        ),
    )


def authorized_video_request(stage="dramatic_structure", **extra):
    registry = video_registry()
    original_request = video_request(stage, **extra)
    profile, schema, budget = (
        registry.profiles[f"video.{stage}.v2"],
        registry.output_schemas[f"output.video_{stage}_stage.v2"],
        registry.step_budgets[f"step_budget.video.{stage}.v2"],
    )
    item = original_request.evidenceBundle.items[0]
    item = item.model_copy(
        update={
            "contentSha256": canonical_execution_sha256(item.contentJson),
            "byteCount": len(canonical_execution_json_bytes(item.contentJson)),
        }
    )
    manifest = EvidenceManifest(
        bundleId=item.bundleId,
        bundleVersion=1,
        itemCount=1,
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentJson", "contentText"}),
            )
        ],
    )
    bundle = original_request.evidenceBundle.model_copy(
        update={
            "items": [item],
            "manifest": manifest,
            "manifestSha256": canonical_execution_sha256(
                manifest.model_dump(mode="json", exclude_none=True)
            ),
            "totalBytes": item.byteCount,
        }
    )
    return rehash_request(
        original_request.model_copy(
            update={
                "evidenceBundle": bundle,
                "modelProfile": ModelProfileRef(
                    profile=profile.key,
                    version=profile.version,
                    reasoningMode=profile.reasoning_mode,
                    deploymentProfileKey=profile.deployment_profile_key,
                    promptProfile=PromptProfileRef(
                        name=profile.prompt_profile.key,
                        version=profile.prompt_profile.version,
                        sha256=profile.prompt_profile.sha256,
                    ),
                ),
                "outputSchema": OutputSchemaRef(
                    name=schema.key,
                    version=schema.version,
                    sha256=schema.sha256,
                    jsonSchema=schema.json_schema_value(),
                ),
                "budget": StepBudget(
                    maxModelCalls=1,
                    maxInputTokens=budget.max_input_tokens,
                    maxPromptCacheMissTokens=budget.max_prompt_cache_miss_tokens,
                    maxCompletionTokens=budget.max_completion_tokens,
                    maxReasoningTokens=0,
                    maxVisibleOutputTokens=budget.max_visible_output_tokens,
                    maxCostMicros=budget.max_cost_micros,
                    maxWallClockSeconds=budget.max_wall_clock_seconds,
                    maxProviderRetries=2,
                    maxProtocolCorrections=1,
                ),
            }
        )
    )


class Responses:
    identity = VideoResponsesIdentity(
        provider="fake",
        model="fake",
        transport_profile="transport.fake.v1",
        endpoint_profile="endpoint.local-fake.v1",
        capability_version="capability.fake.structured-output.v1",
    )

    def __init__(self, *, invalid=False, known_usage=True, error=False, finish="stop"):
        self.calls = 0
        self.invalid, self.known_usage, self.error = invalid, known_usage, error
        self.finish = finish

    async def complete_responses(self, request):
        self.calls += 1
        if self.error:
            raise ProviderTransportError(
                code="http_error", statusCode=429, requestId="rate-limited"
            )
        usage = (
            VideoResponsesUsage(
                inputTokens=100,
                cachedTokens=20,
                promptCacheMissTokens=80,
                completionTokens=50,
                reasoningTokens=0,
                visibleOutputTokens=50,
                totalTokens=150,
                costMicros=0,
            )
            if self.known_usage
            else VideoResponsesUsage()
        )
        return VideoResponsesResult(
            structuredOutput=None if self.invalid else dramatic_result(),
            diagnostic=ModelStructuredOutputDiagnostic(
                code="json_decode_error", jsonPointer="", keyword="type"
            )
            if self.invalid
            else None,
            finishReason=self.finish,
            rawFinishReason="response.completed",
            providerResponseId="response-1",
            usage=usage,
            localSchemaSha256=canonical_execution_sha256(request.structuredOutput.jsonSchema),
            wireSchemaSha256="b" * 64,
        )


async def invoke_video(provider, request=None):
    runtime = ModelRuntime(FakeModelProvider(), responses_provider=provider)
    executor = StatelessExecutionStepExecutor(runtime, responses=runtime, max_output_tokens=48_000)
    request = request or authorized_video_request()
    resolved = executor.resolve(request, video_registry())
    count = 0

    async def begin():
        nonlocal count
        count += 1
        return count

    outcome = await executor.call_provider(
        request,
        executor.build_model_request(request, resolved),
        begin_attempt=begin,
        cancel_event=asyncio.Event(),
    )
    return executor.terminal_from_outcome(request, resolved, outcome), count


@pytest.mark.asyncio
async def test_video_executor_uses_one_independent_responses_call():
    provider = Responses()
    terminal, count = await invoke_video(provider)
    assert terminal.output["outcome"] == "ready"
    assert terminal.usage.inputTokens == 100
    assert terminal.usage.costMicros == 0
    assert provider.calls == count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_only_reliable_complete_responses_can_request_independent_correction(known):
    provider = Responses(invalid=True, known_usage=known)
    terminal, count = await invoke_video(provider)
    assert terminal.errorCode == (
        "VIDEO_STAGE_PROTOCOL_CORRECTION_REQUIRED" if known else "VIDEO_ADAPTATION_OUTPUT_INVALID"
    )
    assert terminal.usage.usageStatus == ("complete" if known else "unknown")
    assert provider.calls == count == 1


@pytest.mark.asyncio
async def test_video_rate_limit_is_not_a_hidden_second_http():
    provider = Responses(error=True)
    terminal, count = await invoke_video(provider)
    assert terminal.errorCategory == "provider_transient"
    assert provider.calls == count == 1


def test_video_enabled_assets_keep_explicit_downline_and_complete_input_budget_guards():
    runtime = ModelRuntime(FakeModelProvider(), responses_provider=Responses())
    executor = StatelessExecutionStepExecutor(runtime, responses=runtime, max_output_tokens=48_000)
    request = authorized_video_request()
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(request, video_registry(enabled=False))
    resolved = executor.resolve(request, video_registry())
    wire = executor.build_model_request(request, resolved)
    size = sum(len(message.content) for message in wire.messages) + len(
        wire.structuredOutput.model_dump_json()
    )
    exact = request.model_copy(
        update={"budget": request.budget.model_copy(update={"maxInputTokens": size})}
    )
    assert executor.build_model_request(exact, resolved).messages == wire.messages
    small = request.model_copy(
        update={"budget": request.budget.model_copy(update={"maxInputTokens": size - 1})}
    )
    with pytest.raises(ExecutionCapabilityError, match="完整视频"):
        executor.build_model_request(small, resolved)


def shot_draft(*, unit="U001", goal="G01", duration=2500):
    return {
        "title": "开门",
        "narrativePurpose": "action",
        "storyFunction": "人物进入房间",
        "audienceGain": "观众确认人物进入",
        "coveredGoalKeys": [goal],
        "sourceRelation": "direct",
        "shotScale": "medium",
        "cameraAngle": "eye_level",
        "cameraMovement": "locked",
        "visualIntent": "林岚推开房门",
        "speechMode": "none",
        "spokenText": None,
        "soundDesign": "门轴摩擦声",
        "cutReason": "人物进入使空间关系改变",
        "timelineDurationMs": duration,
        "sourceUnitIds": [unit],
    }


def ready_candidate():
    return materialize_video_output(
        video_request("shot_design", checkpoint=checkpoint()),
        {"beatsByKey": {"B01": [shot_draft()]}, "suggestedEpisodeBreakAfterShotNumbers": []},
    )["candidate"]


def test_design_and_domain_review_preserve_original_candidate_and_nonblocking_findings():
    candidate = ready_candidate()
    assert candidate["scenes"][0]["beats"][0]["shots"][0]["sourceRanges"] == [
        {"start": 0, "end": 5, "sourceText": "林岚推门。"}
    ]
    request = video_request("cinematic_review", candidate=candidate)
    wire = build_video_request(request, original._review_system_prompt())
    assert SOURCE in wire.messages[1].content
    assert wire.structuredOutput.name == "chapter_cinematic_review_v3"
    assert wire.structuredOutput.jsonSchema["properties"]["findings"]["maxItems"] == 240
    output = materialize_video_output(
        request,
        {
            "decision": "revise",
            "summary": "核心动作需清晰",
            "requiredChanges": ["重新设计进入动作"],
            "findings": [],
        },
    )
    assert output["outcome"] == "ready"
    assert output["review"]["decision"] == "revise"
    assert output["review"]["requiredChanges"] == ["重新设计进入动作"]
    assert "artifactId" not in output


def test_supplement_merges_original_slots_and_clears_old_episode_breaks():
    structure = checkpoint()
    second = {
        **structure["scenes"][0]["beats"][0],
        "beatKey": "B02",
        "sourceUnitIds": ["U002"],
        "coverageGoals": [
            {
                "goalKey": "G02",
                "kind": "story_information",
                "priority": "essential",
                "description": "交接钥匙",
            }
        ],
    }
    structure["scenes"][0]["beats"] = [structure["scenes"][0]["beats"][0], second]
    initial = {"beatsByKey": {"B01": [shot_draft()]}, "suggestedEpisodeBreakAfterShotNumbers": [1]}
    partial = materialize_video_output(video_request("shot_design", checkpoint=structure), initial)
    assert partial["missingBeatKeys"] == ["B02"]
    request = video_request(
        "missing_beat_shots",
        checkpoint=structure,
        design=partial["design"],
        missingBeatKeys=["B02"],
    )
    output = materialize_video_output(
        request,
        {
            "beatsByKey": {"B02": [shot_draft(unit="U002", goal="G02")]},
            "suggestedEpisodeBreakAfterShotNumbers": [1],
        },
    )
    assert output["outcome"] == "ready"
    candidate = output["candidate"]
    assert candidate["suggestedEpisodeBreakAfterShotKeys"] == []
    assert [beat["shots"][0]["shotKey"] for beat in candidate["scenes"][0]["beats"]] == [
        "S01",
        "S02",
    ]
    assert (
        candidate["scenes"][0]["beats"][0]["shots"][0]["visualIntent"]
        == initial["beatsByKey"]["B01"][0]["visualIntent"]
    )


def prompt_request(*, correction=False, findings=None):
    request = video_request(
        "shot_prompt",
        correction=correction,
        correctionFindings=findings or [],
        dependencies=[{"stepId": "previous", "resultHash": "a" * 64}] if correction else [],
    )
    context = {
        "taskId": "task-1",
        "inheritedCheckpoint": None,
        "payload": {
            "workflow": "chapter_shot_prompt_v2",
            "adaptationId": "adaptation-1",
            "projectId": "project-1",
            "shotPlanVersionId": "plan-version-1",
            "sourceText": SOURCE,
            "sourceHash": hashlib.sha256(SOURCE.encode()).hexdigest(),
            "shotPlan": ready_candidate(),
            "episodeBreakAfterShotKeys": [],
            "targetShotKeys": ["S01"],
            "ratio": "9:16",
            "targetLanguage": "zh-CN",
            "settingSnapshot": LongSerialSettingSnapshot.from_entries([]).model_dump(mode="json"),
            "visualReferenceBundles": [{"shotKey": "S01", "references": []}],
            "planningRoute": "responses_json_schema_v1",
            "planningModel": "deepseek-v4-flash",
        },
    }
    item = request.evidenceBundle.items[0].model_copy(update={"contentJson": context})
    return request.model_copy(
        update={
            "operation": "chapter_shot_prompt_v2",
            "evidenceBundle": request.evidenceBundle.model_copy(
                update={"items": [item], "policyVersion": "evidence.video.shot_prompt.v2"}
            ),
        }
    )


def test_prompt_batch_keeps_target_projection_and_soft_warning_after_one_correction():
    request = prompt_request()
    wire = build_video_request(request, original._prompt_system_prompt())
    assert wire.structuredOutput.name == "chapter_shot_prompt_spec_v4"
    assert wire.structuredOutput.jsonSchema["$defs"]["ShotPromptSpecCandidate"]["properties"][
        "shotKey"
    ]["enum"] == ["S01"]
    assert "男人交出钥匙。" not in wire.messages[1].content
    assert (
        "performance"
        not in wire.structuredOutput.jsonSchema["$defs"]["SeedanceShotPromptSpec"]["properties"]
    )
    raw = {
        "prompts": [
            {
                "shotKey": "S01",
                "spec": {
                    "subjectAndScene": "林岚站在书房门口",
                    "visibleAction": "林岚推开房门，承接下一镜",
                    "expressionAndGaze": None,
                    "camera": "中景，固定机位",
                    "audio": "门轴摩擦声",
                    "negativeConstraints": [],
                },
            }
        ]
    }
    first = materialize_video_output(request, raw)
    assert first["outcome"] == "needs_correction"
    assert any(item["code"] == "prompt_neighbor" for item in first["validationFindings"])
    corrected = prompt_request(correction=True, findings=first["validationFindings"])
    second = materialize_video_output(corrected, raw)
    assert second["outcome"] == "ready"
    assert (
        "不得复述、预演或指导上一镜/下一镜"
        in second["promptBatch"]["prompts"][0]["qualityWarnings"]
    )
    assert (
        "必须修正的问题 JSON"
        in build_video_request(corrected, original._prompt_system_prompt()).messages[1].content
    )


def test_semantic_revision_empty_changes_does_not_gain_structural_correction():
    value = VideoShotDesignInput.model_validate(
        {
            "stageKey": "shot_design",
            "cycle": 1,
            "correction": False,
            "dependencies": [{"stepId": "review", "resultHash": "a" * 64}],
            "checkpoint": checkpoint(),
            "requiredChanges": [],
            "correctionFindings": [],
        }
    )
    assert value.cycle == 1 and not value.correction


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["length", "content_filter"])
@pytest.mark.parametrize("known", [True, False])
async def test_original_video_known_incomplete_may_use_one_independent_correction(finish, known):
    provider = Responses(invalid=True, finish=finish, known_usage=known)
    terminal, count = await invoke_video(provider)
    if known:
        assert terminal.errorCode == "VIDEO_STAGE_PROTOCOL_CORRECTION_REQUIRED"
    else:
        assert terminal.errorCategory == "provider_terminal"
    assert provider.calls == count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage", ["missing_beat_shots", "cinematic_review", "corrected", "revised"]
)
async def test_incomplete_never_adds_calls_to_supplement_review_or_consumed_correction(stage):
    if stage == "missing_beat_shots":
        request = authorized_video_request(
            stage,
            checkpoint=checkpoint(),
            design={"beatsByKey": {}, "suggestedEpisodeBreakAfterShotNumbers": []},
            missingBeatKeys=["B01"],
        )
    elif stage == "cinematic_review":
        request = authorized_video_request(stage, candidate=ready_candidate())
    elif stage == "revised":
        request = authorized_video_request(
            "shot_design", cycle=1, checkpoint=checkpoint(), requiredChanges=[]
        )
    else:
        request = authorized_video_request(
            correction=True,
            dependencies=[{"stepId": "previous", "resultHash": "a" * 64}],
            correctionFindings=[
                {"code": "protocol_invalid", "shotKey": None, "parameters": {}, "blocking": True}
            ],
        )
    terminal, count = await invoke_video(Responses(invalid=True, finish="length"), request)
    assert terminal.errorCode == "MODEL_OUTPUT_TRUNCATED"
    assert count == 1


@pytest.mark.asyncio
async def test_unknown_finish_is_not_a_known_incomplete_correction():
    terminal, _ = await invoke_video(Responses(invalid=True, finish="unknown"))
    assert terminal.errorCode == "MODEL_FINISH_REASON_INVALID"


def test_first_review_can_keep_481_findings_and_proceed_to_full_revision():
    candidate = ready_candidate()
    candidate["scenes"][0]["beats"][0]["shots"][0]["timelineDurationMs"] = 500

    def finding(prefix, index):
        return {
            "severity": "notice",
            "scope": "plan",
            "scopeKey": None,
            "message": f"{prefix}{index}",
            "evidence": "原证据",
            "suggestion": "请复核",
        }

    candidate["reviewFindings"] = [finding("旧发现", index) for index in range(240)]
    output = materialize_video_output(
        video_request("cinematic_review", candidate=candidate),
        {
            "decision": "revise",
            "summary": "完整重做",
            "requiredChanges": ["重新设计核心动作"],
            "findings": [finding("新发现", index) for index in range(240)],
        },
    )
    assert output["outcome"] == "ready"
    assert output["review"]["decision"] == "revise"
    assert len(output["review"]["findings"]) == 481
    revision = video_request(
        "shot_design",
        cycle=1,
        checkpoint=checkpoint(),
        requiredChanges=output["review"]["requiredChanges"],
    )
    wire = build_video_request(revision, original._shot_design_system_prompt())
    assert "重新设计核心动作" in wire.messages[1].content
