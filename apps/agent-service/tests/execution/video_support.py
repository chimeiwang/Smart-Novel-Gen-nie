"""新 Episode 视频执行测试共用的请求与供应商夹具。"""

from __future__ import annotations

import asyncio
from typing import Any

from inkforge_agents.execution.executor import StatelessExecutionStepExecutor
from inkforge_agents.execution.registry import load_execution_registry
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

from .support import execution_request, rehash_request


def authorized_video_request(stage: str):
    """按四项 Episode Operation 的冻结资产构造可执行请求。"""

    if stage.startswith("episode_script"):
        operation_name = "episode_script_generate"
    elif stage.startswith("episode_storyboard"):
        operation_name = "episode_storyboard_generate"
    else:
        raise ValueError(f"未知 Episode 视频阶段：{stage}")

    registry = load_execution_registry(environment="test")
    operation = registry.resolve("video", operation_name)
    profile = registry.profiles[f"video.{stage}.v2"]
    schema = registry.output_schemas[f"output.video_{stage}_stage.v2"]
    budget = registry.step_budgets[f"step_budget.video.{stage}.v2"]
    base = execution_request()
    content: dict[str, Any] = {}
    item = base.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": f"video_{stage}_context",
            "resourceId": "episode-1",
            "contentType": "json",
            "contentText": None,
            "contentJson": content,
            "range": None,
            "contentSha256": canonical_execution_sha256(content),
            "byteCount": len(canonical_execution_json_bytes(content)),
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
    bundle = base.evidenceBundle.model_copy(
        update={
            "policyVersion": operation.operation.evidence_policy,
            "items": [item],
            "manifest": manifest,
            "manifestSha256": canonical_execution_sha256(
                manifest.model_dump(mode="json", exclude_none=True)
            ),
            "totalBytes": item.byteCount,
        }
    )
    return rehash_request(
        base.model_copy(
            update={
                "workflow": "video",
                "operation": operation_name,
                "purpose": "generation",
                "lane": operation.operation.lane,
                "input": {
                    "stageKey": stage,
                    "cycle": 0,
                    "candidate": None,
                    "requiredChanges": [],
                    "dependencies": [],
                },
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
                    maxModelCalls=budget.max_model_calls,
                    maxInputTokens=budget.max_input_tokens,
                    maxPromptCacheMissTokens=budget.max_prompt_cache_miss_tokens,
                    maxCompletionTokens=budget.max_completion_tokens,
                    maxReasoningTokens=budget.max_reasoning_tokens,
                    maxVisibleOutputTokens=budget.max_visible_output_tokens,
                    maxCostMicros=budget.max_cost_micros,
                    maxWallClockSeconds=budget.max_wall_clock_seconds,
                    maxProviderRetries=budget.max_provider_retries,
                    maxProtocolCorrections=budget.max_protocol_corrections,
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

    def __init__(
        self,
        *,
        invalid: bool = False,
        known_usage: bool = True,
        error: bool = False,
        finish: str = "stop",
    ) -> None:
        self.calls = 0
        self.invalid = invalid
        self.known_usage = known_usage
        self.error = error
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
            structuredOutput=None if self.invalid else {},
            diagnostic=(
                ModelStructuredOutputDiagnostic(
                    code="json_decode_error", jsonPointer="", keyword="type"
                )
                if self.invalid
                else None
            ),
            finishReason=self.finish,
            rawFinishReason="response.completed",
            providerResponseId="response-1",
            usage=usage,
            localSchemaSha256=canonical_execution_sha256(request.structuredOutput.jsonSchema),
            wireSchemaSha256="b" * 64,
        )


async def invoke_video(provider, request):
    runtime = ModelRuntime(FakeModelProvider(), responses_provider=provider)
    executor = StatelessExecutionStepExecutor(runtime, responses=runtime, max_output_tokens=48_000)
    resolved = executor.resolve(request, load_execution_registry(environment="test"))
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
