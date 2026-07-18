from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from inkforge_agents.graph.state import create_initial_state
from inkforge_agents.short_story.story_graph import (
    ShortStoryGraphDependencies,
    build_short_story_graph,
    extract_complete_short_story,
)
from inkforge_contracts import ShortStoryChapterDraft, count_short_story_text_length

START = "ARTIFACT_OUTPUT_START"
END = "ARTIFACT_OUTPUT_END"


def _response(content: str = "", *, finish_reason: str = "completed") -> dict[str, Any]:
    return {
        "visibleContent": content,
        "controlEvents": [],
        "toolCalls": [],
        "toolResults": [],
        "finishReason": finish_reason,
    }


def _manuscript(content: str) -> str:
    return f"{START}\n{content}\n{END}"


class AgentExecutor:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, int | None]] = []

    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: str,
        operation_kind: str,
    ) -> dict[str, Any]:
        assert operation_kind == "write_short_story"
        self.calls.append(
            (agent_id, execution_mode, state.get("shortStoryArtifactRevision"))
        )
        if not self.responses:
            raise AssertionError("发生了计划外的模型调用")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


class ArtifactPort:
    def __init__(self, artifact: dict[str, Any] | None = None) -> None:
        self.artifact = deepcopy(artifact)
        self.actions: list[tuple[str, Any]] = []
        self.evaluations: list[dict[str, Any]] = []

    async def save_short_story(
        self,
        state: dict[str, Any],
        draft: ShortStoryChapterDraft,
        *,
        user_request: str | None,
    ) -> str:
        revision = 1 if self.artifact is None else int(self.artifact["revision"]) + 1
        artifact_id = "artifact-story"
        artifact_key = "short-story-task-1"
        self.artifact = {
            "id": artifact_id,
            "artifactKey": artifact_key,
            "kind": "chapter_draft",
            "revision": revision,
            "status": "under_review",
            "payload": draft.model_dump(mode="json"),
            "evaluations": [],
        }
        action = "submit" if revision == 1 else "revise"
        self.actions.append(
            (
                action,
                {
                    "revision": revision,
                    "generationCommandId": draft.metadata.generationCommandId,
                    "automaticRewriteCount": draft.metadata.automaticRewriteCount,
                    "generationReason": draft.metadata.generationReason,
                    "userRequest": user_request,
                },
            )
        )
        return artifact_id

    def review_context(self, artifact_id: str) -> dict[str, Any]:
        assert self.artifact is not None and artifact_id == self.artifact["id"]
        return deepcopy(self.artifact)

    async def submit_evaluation(
        self,
        state: dict[str, Any],
        artifact_id: str,
        evaluator: str,
        event: dict[str, Any],
    ) -> None:
        assert self.artifact is not None and artifact_id == self.artifact["id"]
        evaluation = {
            "revision": self.artifact["revision"],
            "evaluatorAgent": evaluator,
            "verdict": event["verdict"],
            "summary": event["summary"],
            "requiredChanges": event.get("requiredChanges"),
        }
        self.evaluations.append(evaluation)
        self.artifact["evaluations"].append(evaluation)
        self.actions.append(("evaluation", (evaluator, self.artifact["revision"])))

    async def mark_awaiting_user(self, artifact_id: str) -> None:
        assert self.artifact is not None and artifact_id == self.artifact["id"]
        self.artifact["status"] = "awaiting_user"
        self.actions.append(("await", self.artifact["revision"]))


def _evaluation(
    verdict: str = "pass",
    *,
    summary: str = "审核通过",
    required_changes: str | None = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "type": "submit_evaluation",
        "verdict": verdict,
        "summary": summary,
    }
    if required_changes is not None:
        arguments["requiredChanges"] = required_changes
    return {
        **_response(),
        "controlEvents": [arguments],
    }


def _state(
    *,
    command_id: str = "job-1",
    run_artifact: dict[str, Any] | None = None,
    resume_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = {
        "kind": "approved_short_outline",
        "outlineArtifactId": "outline-1",
        "outlineRevision": 3,
        "outlineHash": "a" * 64,
    }
    state = create_initial_state(
        task_id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        user_message="请生成完整中短篇正文",
        target_word_count=6000,
        workflow_kind="short_medium",
        explicit_operation="write_short_story",
        command_id=command_id,
        target_total_word_count=6000,
        command_source=source,
    )
    state["currentOperation"] = {
        "kind": "write_short_story",
        "targetType": "chapter",
        "targetId": "chapter-1",
        "userGoal": "请生成完整中短篇正文",
        "primaryAgent": "写作",
        "reviewers": ["编辑", "校验"],
        "outputKind": "chapter_text",
        "requiresArtifact": True,
        "requiresUserApproval": True,
        "confidence": 1.0,
        "reasoning": "Core 显式指定中短篇整稿流程",
    }
    state["resumeDecision"] = resume_decision
    state["runtimeContext"] = {
        "coreContext": {
            "workspace": {},
            "planning": {
                "shortStoryContext": {
                    "approvedOutline": {
                        "artifactId": "outline-1",
                        "revision": 3,
                        "hash": "a" * 64,
                        "payload": {"kind": "short_story_outline"},
                    },
                    "targetTotalWordCount": 6000,
                    "targetChapter": {
                        "id": "chapter-1",
                        "baseContentHash": "b" * 64,
                    },
                },
                "shortStoryRunArtifact": deepcopy(run_artifact),
            },
        },
        "runResource": {
            "userId": "user-1",
            "novelId": "novel-1",
            "taskId": "task-1",
            "runId": "run-1",
            "jobId": command_id,
        },
    }
    return state


def _persisted_artifact(
    *,
    command_id: str = "job-1",
    automatic_rewrite_count: int = 0,
    evaluations: list[dict[str, Any]] | None = None,
    revision: int = 1,
) -> dict[str, Any]:
    content = "已持久化的完整正文，尾声仍在。"
    return {
        "id": "artifact-story",
        "artifactKey": "short-story-task-1",
        "status": "under_review",
        "revision": revision,
        "payload": {
            "kind": "chapter_draft",
            "storyLengthProfile": "short_medium",
            "content": content,
            "metadata": {
                "sourceOutlineArtifactId": "outline-1",
                "sourceOutlineRevision": 3,
                "sourceOutlineHash": "a" * 64,
                "targetWordCount": 6000,
                "actualWordCount": count_short_story_text_length(content),
                "targetChapterId": "chapter-1",
                "baseChapterHash": "b" * 64,
                "generationCommandId": command_id,
                "automaticRewriteCount": automatic_rewrite_count,
                "generationReason": (
                    "automatic_rewrite"
                    if automatic_rewrite_count == 1
                    else "user_request"
                ),
            },
        },
        "evaluations": evaluations or [],
    }


@pytest.mark.parametrize(
    "raw",
    [
        f"前置正文\n{START}\n正文\n{END}",
        f"{START} 正文\n{END}",
        f"{START}\n正文\n{END} 尾注",
        f"{START}\n正文\n{START}\n重复\n{END}",
        f"{START}\n正文\n{END}\n后置正文",
        f"{START}\n   \n{END}",
        "没有边界的正文",
    ],
)
def test_complete_short_story_boundary_rejects_ambiguous_or_partial_text(raw: str) -> None:
    with pytest.raises(ValueError, match="SHORT_STORY_OUTPUT_BOUNDARY_INVALID"):
        extract_complete_short_story(raw)


def test_complete_short_story_boundary_keeps_the_final_paragraph() -> None:
    raw = f"\n\n{START}\n第一段。\n\n尾声不能丢。\n{END}\n"
    assert extract_complete_short_story(raw) == "第一段。\n\n尾声不能丢。"


def test_complete_short_story_boundary_does_not_rewrite_body_whitespace() -> None:
    raw = f"{START}\n  第一行保留缩进。\n尾行保留空格。  \n{END}"
    assert extract_complete_short_story(raw) == "  第一行保留缩进。\n尾行保留空格。  "


@pytest.mark.asyncio
async def test_initial_story_uses_one_writer_call_then_serial_reviews_same_revision() -> None:
    executor = AgentExecutor(
        [
            _response(_manuscript("开端。\n\n尾声完整。")),
            _evaluation(summary="编辑通过"),
            _evaluation(summary="校验通过"),
        ]
    )
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    result = await graph.ainvoke(_state())

    assert executor.calls == [
        ("写作", "primary", None),
        ("编辑", "reviewer", 1),
        ("校验", "reviewer", 1),
    ]
    assert [item[0] for item in artifacts.actions] == [
        "submit",
        "evaluation",
        "evaluation",
        "await",
    ]
    assert result["phase"] == "waiting_user"
    assert "尾声完整" not in repr(result)
    assert result.get("agentOutputs") == {}
    assert result.get("finalResponse") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_reason", ["length", "content_filter", "unknown", "max_iterations"]
)
async def test_non_completed_writer_turn_fails_without_artifact(finish_reason: str) -> None:
    executor = AgentExecutor([_response(_manuscript("半截正文"), finish_reason=finish_reason)])
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    with pytest.raises(RuntimeError, match="SHORT_STORY_GENERATION_INCOMPLETE"):
        await graph.ainvoke(_state())

    assert artifacts.artifact is None
    assert artifacts.actions == []
    assert executor.calls == [("写作", "primary", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("approvedOutline", "artifactId"), "wrong-outline"),
        (("approvedOutline", "revision"), 4),
        (("approvedOutline", "hash"), "c" * 64),
        (("targetTotalWordCount",), 7000),
        (("targetChapter", "id"), "wrong-chapter"),
    ],
)
async def test_authority_identity_mismatch_fails_before_writer_model(
    path: tuple[str, ...], value: object
) -> None:
    state = _state()
    current: dict[str, Any] = state["runtimeContext"]["coreContext"]["planning"][
        "shortStoryContext"
    ]
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    executor = AgentExecutor([])
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    with pytest.raises(ValueError, match="SHORT_STORY_CONTEXT_IDENTITY_MISMATCH"):
        await graph.ainvoke(state)

    assert executor.calls == []
    assert artifacts.actions == []


@pytest.mark.asyncio
async def test_review_issues_trigger_exactly_one_automatic_full_rewrite() -> None:
    executor = AgentExecutor(
        [
            _response(_manuscript("第一版正文。")),
            _evaluation("revise", summary="节奏松散", required_changes="压紧中段"),
            _evaluation(summary="一致性通过"),
            _response(_manuscript("完整返工正文。")),
            _evaluation("revise", summary="仍可加强", required_changes="加强高潮"),
            _evaluation("block", summary="伏笔有遗漏", required_changes="补回伏笔"),
        ]
    )
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    result = await graph.ainvoke(_state())

    assert [call[:2] for call in executor.calls] == [
        ("写作", "primary"),
        ("编辑", "reviewer"),
        ("校验", "reviewer"),
        ("写作", "reviser"),
        ("编辑", "reviewer"),
        ("校验", "reviewer"),
    ]
    saves = [payload for action, payload in artifacts.actions if action in {"submit", "revise"}]
    assert [item["automaticRewriteCount"] for item in saves] == [0, 1]
    assert [item["generationReason"] for item in saves] == [
        "user_request",
        "automatic_rewrite",
    ]
    assert result["phase"] == "waiting_user"
    assert not executor.responses


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_turn",
    [
        _response(_manuscript("被截断的返工稿"), finish_reason="length"),
        _response(_manuscript("被过滤的返工稿"), finish_reason="content_filter"),
        RuntimeError("供应商暂时不可用"),
    ],
    ids=["length", "content-filter", "provider-error"],
)
async def test_failed_automatic_rewrite_keeps_previous_complete_artifact(
    failed_turn: dict[str, Any] | Exception,
) -> None:
    executor = AgentExecutor(
        [
            _response(_manuscript("第一版完整正文，结尾仍在。")),
            _evaluation("revise", summary="节奏松散", required_changes="压紧中段"),
            _evaluation(summary="一致性通过"),
            failed_turn,
        ]
    )
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    with pytest.raises(RuntimeError):
        await graph.ainvoke(_state())

    assert artifacts.artifact is not None
    assert artifacts.artifact["revision"] == 1
    assert artifacts.artifact["payload"]["content"] == "第一版完整正文，结尾仍在。"
    assert [action for action, _payload in artifacts.actions].count("revise") == 0


@pytest.mark.asyncio
async def test_reviewer_exception_and_missing_event_are_persisted_as_blocks() -> None:
    executor = AgentExecutor(
        [
            _response(_manuscript("第一版正文。")),
            RuntimeError("编辑暂不可用"),
            _response(),
            _response(_manuscript("自动返工正文。")),
            _evaluation(),
            _evaluation(),
        ]
    )
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    await graph.ainvoke(_state())

    first_round = [item for item in artifacts.evaluations if item["revision"] == 1]
    assert [(item["evaluatorAgent"], item["verdict"]) for item in first_round] == [
        ("编辑", "block"),
        ("校验", "block"),
    ]
    assert "暂时不可用" in first_round[0]["summary"]
    assert "未提交结构化结论" in first_round[1]["summary"]


@pytest.mark.asyncio
async def test_revise_review_without_required_changes_is_persisted_as_block() -> None:
    executor = AgentExecutor(
        [
            _response(_manuscript("第一版正文。")),
            _evaluation("revise", summary="只说不好但不给修改项"),
            _evaluation(),
            _response(_manuscript("自动返工正文。")),
            _evaluation(),
            _evaluation(),
        ]
    )
    artifacts = ArtifactPort()
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    await graph.ainvoke(_state())

    first_editor = next(
        item
        for item in artifacts.evaluations
        if item["revision"] == 1 and item["evaluatorAgent"] == "编辑"
    )
    assert first_editor["verdict"] == "block"
    assert "未提交结构化结论" in first_editor["summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("evaluations", "automatic_count", "expected_agents"),
    [
        ([], 0, ["编辑", "校验"]),
        (
            [
                {
                    "revision": 1,
                    "evaluatorAgent": "编辑",
                    "verdict": "pass",
                    "summary": "通过",
                }
            ],
            0,
            ["校验"],
        ),
        (
            [
                {
                    "revision": 1,
                    "evaluatorAgent": "编辑",
                    "verdict": "revise",
                    "summary": "需修改",
                    "requiredChanges": "压紧节奏",
                },
                {"revision": 1, "evaluatorAgent": "校验", "verdict": "pass", "summary": "通过"},
            ],
            0,
            ["写作", "编辑", "校验"],
        ),
        (
            [
                {
                    "revision": 2,
                    "evaluatorAgent": "编辑",
                    "verdict": "revise",
                    "summary": "仍需修改",
                },
                {
                    "revision": 2,
                    "evaluatorAgent": "校验",
                    "verdict": "block",
                    "summary": "仍有冲突",
                },
            ],
            1,
            [],
        ),
    ],
)
async def test_persistent_recovery_skips_completed_generation_and_review_stages(
    evaluations: list[dict[str, Any]],
    automatic_count: int,
    expected_agents: list[str],
) -> None:
    revision = 2 if automatic_count else 1
    artifact = _persisted_artifact(
        automatic_rewrite_count=automatic_count,
        evaluations=evaluations,
        revision=revision,
    )
    responses: list[dict[str, Any] | Exception] = []
    for agent in expected_agents:
        if agent == "写作":
            responses.append(_response(_manuscript("恢复后的完整自动返工稿。")))
        else:
            responses.append(_evaluation())
    executor = AgentExecutor(responses)
    artifacts = ArtifactPort(artifact)
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    result = await graph.ainvoke(_state(run_artifact=artifact))

    assert [agent for agent, _, _ in executor.calls] == expected_agents
    assert result["phase"] == "waiting_user"
    assert not executor.responses


@pytest.mark.asyncio
async def test_new_user_revision_resets_automatic_rewrite_budget_for_new_command() -> None:
    old_artifact = _persisted_artifact(
        command_id="old-command",
        automatic_rewrite_count=1,
        revision=2,
        evaluations=[
            {"revision": 2, "evaluatorAgent": "编辑", "verdict": "pass", "summary": "通过"},
            {"revision": 2, "evaluatorAgent": "校验", "verdict": "pass", "summary": "通过"},
        ],
    )
    executor = AgentExecutor(
        [
            _response(_manuscript("用户要求后的完整改稿。")),
            _evaluation("revise", required_changes="加强结局", summary="结局偏弱"),
            _evaluation(),
            _response(_manuscript("本命令唯一一次自动返工稿。")),
            _evaluation(),
            _evaluation(),
        ]
    )
    artifacts = ArtifactPort(old_artifact)
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    result = await graph.ainvoke(
        _state(
            command_id="job-2",
            run_artifact=old_artifact,
            resume_decision={
                "decision": "revise",
                "artifactId": "artifact-story",
                "userMessage": "  结局改得更克制\n",
            },
        )
    )

    saves = [payload for action, payload in artifacts.actions if action == "revise"]
    assert [item["automaticRewriteCount"] for item in saves] == [0, 1]
    assert saves[0]["userRequest"] == "  结局改得更克制\n"
    assert saves[1]["userRequest"] is None
    assert result["phase"] == "waiting_user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "status"),
    [("approve", "applied"), ("discard", "discarded")],
)
async def test_approve_or_discard_resume_uses_zero_models_and_zero_artifact_calls(
    decision: str, status: str
) -> None:
    old_artifact = _persisted_artifact(
        command_id="old-command",
        automatic_rewrite_count=1,
        revision=2,
    )
    executor = AgentExecutor([])
    artifacts = ArtifactPort(old_artifact)
    graph = build_short_story_graph(
        ShortStoryGraphDependencies(agentExecutor=executor, artifacts=artifacts)
    )

    result = await graph.ainvoke(
        _state(
            command_id="job-2",
            run_artifact=old_artifact,
            resume_decision={
                "decision": decision,
                "artifactId": "artifact-story",
            },
        )
    )

    assert executor.calls == []
    assert artifacts.actions == []
    assert result["phase"] == "completed"
    assert result["artifactStatus"] == status
