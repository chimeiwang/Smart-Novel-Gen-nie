from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_contracts.execution import ModelProfileRef, PromptProfileRef

from .support import rehash_request
from .test_chapter_draft import _request
from .test_executor import RecordingModel, _one_attempt


@pytest.mark.parametrize("role", ["consistency", "editorial"])
@pytest.mark.parametrize("dispatch_mode", ["initial", "pending_recovery", "running_recovery"])
@pytest.mark.parametrize("operation", ["write_chapter", "rewrite_scene"])
def test_历史正文复审首次派发与恢复继续使用原v1提示词(role, dispatch_mode, operation) -> None:
    registry = load_execution_registry(environment="test")
    old_profile = registry.profiles[f"reviewer.chapter_draft_{role}.v1"]
    request = _request(reviewer=f"reviewer.chapter_draft_{role}.v2", operation_name=operation)
    request = rehash_request(
        request.model_copy(
            update={
                "dispatchMode": dispatch_mode,
                "modelProfile": ModelProfileRef(
                    profile=old_profile.key,
                    version=old_profile.version,
                    reasoningMode=old_profile.reasoning_mode,
                    deploymentProfileKey=old_profile.deployment_profile_key,
                    promptProfile=PromptProfileRef(
                        name=old_profile.prompt_profile.key,
                        version=old_profile.prompt_profile.version,
                        sha256=old_profile.prompt_profile.sha256,
                    ),
                ),
            }
        )
    )
    model = RecordingModel()
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=100_000)
    resolved = executor.resolve(request, registry)
    outgoing = executor.build_model_request(request, resolved)
    assert resolved.profile.key == old_profile.key
    assert outgoing.messages[0].content == old_profile.prompt_profile.system_prompt
    assert outgoing.messages[0].content != registry.prompt_profiles[
        f"prompt.reviewer.chapter_draft_{role}.v2"
    ].system_prompt
    assert model.requests == []


def test_首次派发不允许混合新旧复审引用() -> None:
    registry = load_execution_registry(environment="test")
    request = _request(reviewer="reviewer.chapter_draft_editorial.v2")
    request = rehash_request(
        request.model_copy(
            update={
                "modelProfile": request.modelProfile.model_copy(
                    update={
                        "profile": "reviewer.chapter_draft_editorial.v1",
                        "version": 1,
                    }
                )
            }
        )
    )
    model = RecordingModel()
    executor = StatelessExecutionStepExecutor(model, max_output_tokens=100_000)
    with pytest.raises(ExecutionCapabilityError):
        executor.resolve(request, registry)
    assert model.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["pass_with_seven_findings", "null_patch", "valid_issues"])
async def test_正文复审保持严格校验并记录实际失败路径(case, caplog) -> None:
    registry = load_execution_registry(environment="test")
    request = _request(reviewer="reviewer.chapter_draft_editorial.v2")
    evidence = request.evidenceBundle.items[0]
    finding = {
        "dimension": "chapter_draft.local",
        "severity": "warning",
        "claim": "private-claim-小说问题",
        "candidateRange": None,
        "evidence": [
            {
                "evidenceItemId": evidence.id,
                "contentSha256": evidence.contentSha256,
                "range": None,
            }
        ],
        "suggestion": "private-suggestion-修改建议",
        "confidence": 0.9,
    }
    output = {"contentVerdict": "issues_found", "findings": [finding]}
    if case == "pass_with_seven_findings":
        output = {"contentVerdict": "pass", "findings": [finding] * 7}
    elif case == "null_patch":
        finding["candidatePatch"] = None
    calls = []

    async def respond(http_request: httpx.Request) -> httpx.Response:
        calls.append(http_request)
        wire = json.loads(http_request.content)
        assert wire["response_format"] == {"type": "json_object"}
        assert wire["thinking"] == {"type": "disabled"}
        assert wire["max_tokens"] == 100_000
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": json.dumps(output, ensure_ascii=False)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    settings = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "openai_compatible",
            "openai_api_key": "private-api-secret",
            "openai_base_url": "https://api.deepseek.com",
            "openai_model": "deepseek-v4-flash",
        }
    )
    with caplog.at_level(logging.WARNING):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            executor = StatelessExecutionStepExecutor(
                ModelRuntime(DeepSeekV4Provider(settings, client=http)),
                max_output_tokens=100_000,
            )
            resolved = executor.resolve(request, registry)
            outcome = await executor.call_provider(
                request,
                executor.build_model_request(request, resolved),
                begin_attempt=_one_attempt,
                cancel_event=asyncio.Event(),
            )
            terminal = executor.terminal_from_outcome(request, resolved, outcome)

    assert len(calls) == terminal.usage.providerAttempts == 1
    assert terminal.usage.protocolCorrections == 0
    if case == "valid_issues":
        assert terminal.resultKind == "evaluation"
        assert terminal.evaluation.contentVerdict == "issues_found"
        assert terminal.evaluation.findings[0].claim == finding["claim"]
        assert not caplog.records
    else:
        assert terminal.errorCode == "MODEL_STRUCTURED_OUTPUT_INVALID"
        assert terminal.retryable is False
        pointer, keyword = (
            ("/findings", "maxItems")
            if case == "pass_with_seven_findings"
            else ("/findings/0/candidatePatch", "type")
        )
        assert f"pointer={pointer} keyword={keyword}" in caplog.text
        assert outcome.result.content == ""
        assert outcome.result.structuredOutput is None
    for secret in ("private-", finding["claim"], finding["suggestion"]):
        assert secret not in caplog.text
