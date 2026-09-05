"""视频隔离验收夹具必须通过真实阶段物化，不能凭自造终态证明业务完成。"""

from __future__ import annotations

import hashlib
import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from inkforge_agents.execution.video import build_video_request, materialize_video_output
from inkforge_agents.jobs import video_adaptation as original
from inkforge_agents.providers.video_responses import VideoResponsesRequest
from inkforge_contracts.execution import canonical_execution_sha256
from inkforge_contracts.video import LongSerialSettingSnapshot
from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationPromptJobPayload,
)
from inkforge_contracts.video_execution import VideoTaskContextV2
from pydantic import SecretStr

from . import video_fixture
from .run_e2e import ComposeStack
from .video import _database, _run_id, assert_video_facts
from .video_fixture import (
    FAKE_IDENTITY,
    SOURCE,
    TITLE,
    compiled_prompt,
    request_identity,
    video_result,
)


def _payload():
    return ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle=TITLE,
        sourceText=SOURCE,
        sourceHash=hashlib.sha256(SOURCE.encode()).hexdigest(),
        ratio="16:9",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )


def _stage(stage, payload, previous, **extra):
    context = VideoTaskContextV2(taskId="task-1", payload=payload, inheritedCheckpoint=None)
    data = {
        "stageKey": stage,
        "cycle": 0,
        "correction": False,
        "dependencies": [
            {"stepId": item["id"], "resultHash": item["resultHash"]} for item in previous
        ],
        **extra,
    }
    if stage in {"dramatic_structure", "shot_design", "shot_prompt"}:
        data.setdefault("correctionFindings", [])
    if stage == "shot_design":
        data.setdefault("requiredChanges", [])
    prompt = stage == "shot_prompt"
    return SimpleNamespace(
        stepId=f"step-{len(previous)}",
        workflow="video",
        operation=payload.workflow,
        purpose="generation",
        novelId="novel-1",
        lane="batch_media",
        artifactId=None,
        artifactRevision=None,
        input=data,
        modelProfile=SimpleNamespace(profile=f"video.{stage}.v2", version=2),
        outputSchema=SimpleNamespace(name=f"output.video_{stage}_stage.v2", version=2),
        evidenceBundle=SimpleNamespace(
            policyVersion="evidence.video.shot_prompt.v2"
            if prompt
            else "evidence.video.chapter_adaptation.v2",
            items=[
                SimpleNamespace(
                    resourceType="video_task_context",
                    resourceId="task-1",
                    exists=True,
                    contentType="json",
                    range=None,
                    contentJson=context.model_dump(mode="json"),
                )
            ],
        ),
        budget=SimpleNamespace(maxVisibleOutputTokens=48_000),
    )


def _model_request(stage):
    system_prompt = {
        "dramatic_structure": original._dramatic_system_prompt,
        "shot_design": original._shot_design_system_prompt,
        "cinematic_review": original._review_system_prompt,
        "shot_prompt": original._prompt_system_prompt,
    }[stage.input["stageKey"]]()
    return VideoResponsesRequest.from_turn(build_video_request(stage, system_prompt))


def _execute(stage):
    wire = _model_request(stage)
    result = video_result(wire)
    output = materialize_video_output(stage, result.structuredOutput)
    usage = result.usage.model_dump(mode="json", exclude={"totalTokens"})
    # Core Step 命名 inputTokens；测试供应商本身不补计费记录。
    usage.update(usageStatus="complete", providerAttempts=1, protocolCorrections=0)
    return {
        "id": stage.stepId,
        "status": "completed",
        "purpose": "generation",
        "input": stage.input,
        "output": output,
        "bundleId": "bundle-1",
        "profile": stage.modelProfile.profile,
        "model": {
            "provider": "fake",
            "model": "fake",
            "transportProfile": "transport.fake.v1",
            "endpointProfile": "endpoint.local-fake.v1",
            "structuredOutputRoute": "responses_json_schema_v1",
            "capabilityVersion": "capability.fake.structured-output.v1",
            "reasoningMode": "disabled",
            "supportsRequestIdempotency": False,
        },
        "usage": usage,
        "requestHash": canonical_execution_sha256(stage.input),
        "resultHash": canonical_execution_sha256(output),
        "fencingToken": 1,
    }


def _plan_steps():
    payload = _payload()
    first = _execute(_stage("dramatic_structure", payload, []))
    assert first["output"]["outcome"] == "ready"
    second = _execute(
        _stage("shot_design", payload, [first], checkpoint=first["output"]["checkpoint"])
    )
    assert second["output"]["outcome"] == "ready"
    third = _execute(
        _stage(
            "cinematic_review", payload, [first, second], candidate=second["output"]["candidate"]
        )
    )
    return payload, [first, second, third]


def _prompt_steps():
    plan, steps = _plan_steps()
    payload = ChapterAdaptationPromptJobPayload(
        workflow="chapter_shot_prompt_v2",
        adaptationId=plan.adaptationId,
        projectId=plan.projectId,
        shotPlanVersionId="plan-version-1",
        sourceText=SOURCE,
        sourceHash=plan.sourceHash,
        shotPlan=steps[1]["output"]["candidate"],
        episodeBreakAfterShotKeys=[],
        targetShotKeys=["S01"],
        ratio="16:9",
        targetLanguage="zh-CN",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
        visualReferenceBundles=[{"shotKey": "S01", "references": []}],
    )
    first = _execute(_stage("shot_prompt", payload, []))
    second = _execute(
        _stage(
            "shot_prompt",
            payload,
            [first],
            correction=True,
            correctionFindings=first["output"]["validationFindings"],
        )
    )
    return payload, [first, second]


def test_plan_fixture_follows_three_real_single_stage_requests_and_full_dynamic_schema():
    payload, steps = _plan_steps()
    assert len(steps) == 3
    assert [item["output"]["outcome"] for item in steps] == ["ready"] * 3
    assert steps[2]["output"]["review"]["decision"] == "pass"
    candidate = steps[1]["output"]["candidate"]
    assert candidate["sourceHash"] == payload.sourceHash
    assert len(candidate["scenes"]) == 1
    shot = candidate["scenes"][0]["beats"][0]["shots"][0]
    assert shot["shotKey"] == "S01" and shot["visualIntent"] == SOURCE
    assert shot["timelineDurationMs"] == 4000
    assert steps[2]["input"]["candidate"] == candidate
    assert FAKE_IDENTITY.provider == FAKE_IDENTITY.model == "fake"
    assert FAKE_IDENTITY.supports_request_idempotency is False


def test_prompt_fixture_triggers_only_typed_budget_reason_and_one_complete_correction():
    payload, steps = _prompt_steps()
    expected = {
        "code": "prompt_budget",
        "shotKey": "S01",
        "parameters": {"actual": len(compiled_prompt(correction=False)), "maximum": 480},
        "blocking": True,
    }
    assert steps[0]["output"]["outcome"] == "needs_correction"
    assert steps[0]["output"]["validationFindings"] == [expected]
    assert steps[1]["input"]["correctionFindings"] == [expected]
    assert steps[1]["output"]["outcome"] == "ready"
    assert steps[1]["output"]["validationFindings"] == []
    assert len(compiled_prompt(correction=False)) > 480
    assert len(compiled_prompt(correction=True)) <= 480
    first = _model_request(_stage("shot_prompt", payload, []))
    second = _model_request(
        _stage("shot_prompt", payload, [steps[0]], correction=True, correctionFindings=[expected])
    )
    assert request_identity(first) != request_identity(second)
    assert request_identity(first) == request_identity(first.model_copy(deep=True))
    assert "编译后" in second.messages[1].content and "480 字上限" in second.messages[1].content


def test_provider_result_keeps_raw_structure_reliable_usage_and_both_schema_hashes():
    wire = _model_request(_stage("dramatic_structure", _payload(), []))
    result = video_result(wire)
    assert result.diagnostic is None
    assert result.structuredOutput == video_fixture.dramatic()
    assert result.providerResponseId.startswith("e2e-video-")
    assert result.usage.inputTokens == result.usage.promptCacheMissTokens > 0
    assert result.usage.completionTokens == result.usage.visibleOutputTokens > 0
    assert result.usage.cachedTokens == result.usage.reasoningTokens == result.usage.costMicros == 0
    assert result.usage.totalTokens == result.usage.inputTokens + result.usage.completionTokens
    assert len(result.localSchemaSha256) == len(result.wireSchemaSha256) == 64


@pytest.mark.parametrize("mutation", ["stage", "source", "dynamic_enum"])
def test_fixture_rejects_changed_stage_source_and_dynamic_schema(mutation):
    wire = _model_request(_stage("dramatic_structure", _payload(), []))
    data = wire.model_dump(mode="json")
    if mutation == "stage":
        data["structuredOutput"]["name"] = "unknown"
    elif mutation == "source":
        data["messages"][1]["content"] = data["messages"][1]["content"].replace(SOURCE, SOURCE[:-2])
    else:
        data["structuredOutput"]["jsonSchema"]["$defs"]["DramaticBeatDraft"]["properties"][
            "sourceUnitIds"
        ]["items"]["enum"] = ["U002"]
    with pytest.raises(ValueError):
        video_result(VideoResponsesRequest.model_validate(data))


@pytest.mark.asyncio
async def test_controlled_responses_use_original_hash_only_gates(monkeypatch):
    calls = []
    options = []

    class ControlClient:
        def __init__(self, **kwargs):
            options.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, path, *, json):
            calls.append((path, json))
            return httpx.Response(
                200, json={}, request=httpx.Request("POST", "http://control" + path)
            )

    monkeypatch.setattr(video_fixture.httpx, "AsyncClient", ControlClient)
    provider = video_fixture.ControlledVideoResponsesProvider(
        control_url="http://control", control_token="t" * 40
    )
    wire = _model_request(_stage("dramatic_structure", _payload(), []))
    result = await provider.complete_responses(wire)
    assert result.structuredOutput == video_fixture.dramatic()
    assert calls == [
        ("/control/provider/reached", request_identity(wire)),
        ("/control/provider/completed", request_identity(wire)),
    ]
    assert options[0]["trust_env"] is False
    assert options[0]["headers"] == {"X-InkForge-E2E-Token": "t" * 40}
    assert SOURCE not in json.dumps(calls, ensure_ascii=False) and "t" * 40 not in json.dumps(calls)


def _good_facts(prompt_run=False):
    payload, steps = _prompt_steps() if prompt_run else _plan_steps()
    context = VideoTaskContextV2(taskId="task-1", payload=payload, inheritedCheckpoint=None)
    count = len(steps)
    result = (
        {"promptBatch": steps[-1]["output"]["promptBatch"]}
        if prompt_run
        else {"candidate": steps[1]["output"]["candidate"]}
    )
    return {
        "engineVersion": 2,
        "workflow": "video",
        "operation": payload.workflow,
        "status": "completed",
        "novelId": "novel-1",
        "chapterId": None,
        "writingSessionId": None,
        "sourceType": "video_adaptation_task_v2",
        "sourceId": "task-1",
        "targetType": "video_shot_prompt" if prompt_run else "video_adaptation",
        "targetId": "adaptation-1",
        "input": {"taskId": "task-1"},
        "output": {"taskId": "task-1", "artifactId": None if prompt_run else "artifact-1"},
        "taskId": "task-1",
        "taskStatus": "completed",
        "taskJobId": "video-task-job-1",
        "taskAttemptCount": 0,
        "taskRequest": payload.model_dump(mode="json"),
        "taskResult": result,
        "checkpointStage": "none" if prompt_run else "dramatic_structure",
        "checkpoint": None if prompt_run else steps[0]["output"]["checkpoint"],
        "stepCount": count,
        "completedStepCount": count,
        "terminalEventCount": 1,
        "completedPayload": {"outcomeType": "video_task", "resultId": "task-1"},
        "bundleCount": 1,
        "evidence": [
            {
                "kind": "video_task_context",
                "resourceId": "task-1",
                "content": context.model_dump(mode="json"),
            }
        ],
        "reservationCount": count,
        "matchedBillingCount": count,
        "tokenUsageCount": count,
        "creditLedgerCount": 0,
        "userBalanceMicros": 123456789,
        "legacyRunCount": 0,
        "legacyVideoTaskCount": 0,
        "evaluationCount": 0,
        "artifacts": []
        if prompt_run
        else [
            {
                "id": "artifact-1",
                "status": "awaiting_user",
                "kind": "video_adaptation_plan",
                "taskId": "task-1",
                "payload": result,
            }
        ],
        "planVersionCount": 1 if prompt_run else 0,
        "promptVersionCount": 0,
        "steps": steps,
    }


@pytest.mark.parametrize("prompt_run", [False, True])
def test_full_video_database_evidence_and_zero_balance_change(prompt_run):
    result = assert_video_facts(
        _good_facts(prompt_run),
        novel_id="novel-1",
        prompt_run=prompt_run,
        initial_balance=123456789,
    )
    assert result["balanceUnchanged"] and result["balanceDeltaMicros"] == 0
    assert result["stepCount"] == (2 if prompt_run else 3)
    assert SOURCE not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize(
    "path,value",
    [
        (("stepCount",), 4),
        (("terminalEventCount",), 2),
        (("matchedBillingCount",), 0),
        (("taskAttemptCount",), 1),
        (("planVersionCount",), 1),
        (("legacyRunCount",), 1),
        (("legacyVideoTaskCount",), 1),
        (("userBalanceMicros",), 123456788),
        (("taskRequest", "sourceText"), SOURCE[:-1]),
        (("steps", 1, "input", "dependencies", 0, "resultHash"), "b" * 64),
        (("steps", 0, "model", "provider"), "deepseek"),
        (("steps", 0, "model", "supportsRequestIdempotency"), True),
        (("steps", 0, "usage", "providerAttempts"), 2),
        (("steps", 0, "usage", "usageStatus"), "partial"),
        (("steps", 0, "usage", "reasoningTokens"), 1),
        (("artifacts", 0, "taskId"), "different-task"),
        (("completedPayload", "resultId"), "step-0"),
    ],
)
def test_database_assertion_rejects_shadows_replay_wrong_identity_and_premature_writes(path, value):
    raw = deepcopy(_good_facts())
    cursor = raw
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(AssertionError):
        assert_video_facts(raw, novel_id="novel-1", prompt_run=False, initial_balance=123456789)


def test_prompt_correction_rejects_lost_specific_reason():
    raw = _good_facts(True)
    raw["steps"][1]["input"]["correctionFindings"] = []
    with pytest.raises(AssertionError):
        assert_video_facts(raw, novel_id="novel-1", prompt_run=True, initial_balance=123456789)


def test_database_query_is_read_only_scoped_and_binds_original_video_task_fk():
    calls = []
    raw = _good_facts()

    def psql(sql, *, variables):
        calls.append(sql)
        assert variables == {"e2e_run_id": "run-1"}
        return json.dumps(raw)

    assert _database(SimpleNamespace(stack=SimpleNamespace(psql=psql)), "run-1") == raw
    sql = calls[0]
    assert "WHERE r.id=:'e2e_run_id'" in sql
    assert 'WHERE "videoAdaptationTaskId"=t.id' in sql
    assert 'u."taskId"=s.id' in sql and '"providerAttempts"' not in sql
    for token in (
        "promptTokens",
        "cachedTokens",
        "promptCacheMissTokens",
        "completionTokens",
        "reasoningTokens",
        "visibleOutputTokens",
        "totalTokens",
    ):
        assert token in sql
    assert all(word not in sql.upper() for word in ("INSERT ", "UPDATE ", "DELETE "))


@pytest.mark.parametrize("value", ["", "run-1\nrun-2"])
def test_task_lookup_rejects_missing_or_multiple_v2_runs(value):
    stack = SimpleNamespace(psql=lambda *_args, **_kwargs: value)
    with pytest.raises(AssertionError):
        _run_id(SimpleNamespace(stack=stack), "task-1")


@pytest.mark.parametrize("enabled", [False, True])
def test_test_app_injects_responses_only_for_explicit_video_phase(monkeypatch, enabled):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    module = importlib.import_module("agent_app")
    settings = SimpleNamespace(
        environment="test",
        e2e_execution_control_url="http://control",
        e2e_execution_control_token=SecretStr("t" * 40),
    )
    monkeypatch.setattr(module, "Settings", lambda: settings)
    monkeypatch.setattr(module, "create_inkforge_app", lambda **kwargs: kwargs)
    monkeypatch.setenv("E2E_VIDEO_RESPONSES_ENABLED", "true" if enabled else "false")
    result = module.create_app()
    assert ("responses_provider" in result) is enabled
    assert result["settings"] is settings
    if enabled:
        assert result["responses_provider"].identity == FAKE_IDENTITY


def test_video_phase_enables_only_local_video_model_dispatch_and_original_author_paths():
    folder = Path(__file__).parent
    override = yaml.safe_load((folder / "compose.video.yaml").read_text())
    assert set(override) == {"services"}
    core = override["services"]["core-api"]["environment"]
    assert core["VIDEO_PREVIEW_ENABLED"] == core["VIDEO_DISPATCH_ENABLED"] == "true"
    assert core["VIDEO_DISPATCH_NAMESPACE"] == "e2e-video"
    assert core["SEEDANCE_CONFIGURED"] == core["SEEDANCE_ENABLED"] == "false"
    agent = override["services"]["agent-service"]["environment"]
    assert agent["E2E_VIDEO_RESPONSES_ENABLED"] == "true" and agent["SEEDANCE_ENABLED"] == "false"
    stack = SimpleNamespace(
        docker="docker", project="test", rag_embeddings=False, video_responses=False
    )
    original_command = ComposeStack.command.fget(stack)
    stack.video_responses = True
    assert ComposeStack.command.fget(stack) == original_command + [
        "-f",
        str(folder / "compose.video.yaml"),
    ]
    source = (folder / "video.py").read_text()
    for path in (
        "/shot-plan-runs",
        "/shot-plan/confirm",
        "/prompt-runs",
        "/shots/{shot['id']}/prompt",
    ):
        assert path in source
    assert 'restart_and_wait("agent-service")' in source and "minimum_reached=2" in source
    assert "terminalPayloadPresent" in source and '"sourceTaskId"' in source
    assert 'phase == "video"' in (folder / "run_e2e.py").read_text()
