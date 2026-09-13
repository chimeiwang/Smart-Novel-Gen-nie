"""route-off 下旧 Web V1 LangGraph 的最小真实闭环隔离验收。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .run_e2e import Scenario

if TYPE_CHECKING:
    from .run_e2e import Acceptance


def _documents(acceptance: Acceptance) -> dict[str, object]:
    raw = acceptance.stack.psql(
        """
        SELECT json_build_object(
          'chapter', (SELECT content FROM public."Chapter" WHERE id = :'e2e_chapter_id'),
          'outline', (SELECT content FROM public."Outline"
            WHERE "novelId" = :'e2e_novel_id' ORDER BY id LIMIT 1)
        )::text;
        """,
        variables={
            "e2e_chapter_id": acceptance.chapter_id,
            "e2e_novel_id": acceptance.novel_id,
        },
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AssertionError("V1 文档保护快照不是对象")
    return value


def _wait_for_review(acceptance: Acceptance, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        value = acceptance.request(
            "GET", f"/api/v1/writing/runs/{task_id}", expected=200
        ).json()
        if not isinstance(value, dict):
            raise AssertionError("V1 状态响应不是对象")
        last = value
        if (
            value.get("phase") == "awaiting_user_review"
            and isinstance(value.get("activeArtifactId"), str)
        ):
            return value
        if value.get("phase") in {"error", "completed"}:
            raise AssertionError(f"V1 LangGraph 未进入待审状态：{value}")
        time.sleep(0.2)
    raise AssertionError(f"V1 LangGraph 未在门限内进入待审状态：{last.get('phase')}")


def _wait_for_completion(acceptance: Acceptance, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        value = acceptance.request(
            "GET", f"/api/v1/writing/runs/{task_id}", expected=200
        ).json()
        if not isinstance(value, dict):
            raise AssertionError("V1 完成状态响应不是对象")
        last = value
        if value.get("phase") in {"completed", "error"}:
            return value
        time.sleep(0.2)
    raise AssertionError(f"V1 LangGraph 采用后未在门限内完成：{last.get('phase')}")


def scenarios(acceptance: Acceptance) -> Iterator[Scenario]:
    before = _documents(acceptance)
    if not isinstance(before.get("outline"), str):
        raise AssertionError("隔离小说缺少可保护的大纲")
    session_id = acceptance.create_session("legacy-langgraph")
    start_body = {
        "clientRequestId": "e2e-legacy-langgraph-start-01",
        "novelId": acceptance.novel_id,
        "chapterId": acceptance.chapter_id,
        "writingSessionId": session_id,
        "targetWordCount": 1000,
        "selectedAgents": ["写作"],
        "userMessage": "请生成正文，保留当前章节事实。",
    }
    started = acceptance.start_run(start_body).json()
    if not isinstance(started, dict) or started.get("engineVersion") != 1:
        raise AssertionError("旧 Web 请求没有创建 engineVersion=1 任务")
    task_id = started.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        raise AssertionError("V1 启动响应缺少 taskId")

    waiting = _wait_for_review(acceptance, task_id)
    artifact_id = waiting.get("activeArtifactId")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise AssertionError("V1 待审状态缺少 activeArtifactId")
    artifact = acceptance.request(
        "GET", f"/api/v1/writing/tasks/{task_id}/artifact", expected=200
    ).json()
    if not isinstance(artifact, dict):
        raise AssertionError("V1 待审草案响应不是对象")
    if artifact.get("id") != artifact_id or artifact.get("engineVersion") != 1:
        raise AssertionError("V1 待审草案身份或引擎版本无效")
    artifact_key = artifact.get("artifactKey")
    if not isinstance(artifact_key, str) or not artifact_key:
        raise AssertionError("V1 待审草案缺少真实 artifactKey")
    payload = artifact.get("payload")
    candidate = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(candidate, str) or not candidate:
        raise AssertionError("V1 待审草案缺少完整正文")

    state = acceptance.control_state()
    gateway_calls = state.get("gatewayCalls")
    if not isinstance(gateway_calls, list):
        raise AssertionError("E2E 控制器没有记录工具网关调用")
    matching_calls = [
        call
        for call in gateway_calls
        if isinstance(call, dict)
        and call.get("task_id") == task_id
        and call.get("run_id") == task_id
    ]
    tool_names = {call.get("tool_name") for call in matching_calls}
    if "get_writing_context" not in tool_names:
        raise AssertionError("V1 LangGraph 没有通过工具网关读取写作上下文")

    decision = acceptance.request(
        "POST",
        f"/api/v1/review-artifacts/{artifact_id}/decision",
        expected=202,
        json_body={
            "clientRequestId": "e2e-legacy-langgraph-approve-01",
            "decision": "approve",
            "engineVersion": 1,
            "expectedRevision": artifact.get("revision"),
        },
    ).json()
    if not isinstance(decision, dict) or decision.get("engineVersion") != 1:
        raise AssertionError("V1 显式采用没有返回 engineVersion=1 回执")
    terminal = _wait_for_completion(acceptance, task_id)
    if terminal.get("phase") != "completed":
        raise AssertionError(f"V1 草案采用没有完成：{terminal}")
    after = _documents(acceptance)
    if after.get("chapter") != candidate:
        raise AssertionError("采用后的正式正文与待审草案不完全一致")
    if after.get("outline") != before.get("outline"):
        raise AssertionError("V1 正文采用意外修改了大纲")
    return_facts = {
        "start": started,
        "waiting": waiting,
        "artifact": {
            "id": artifact_id,
            "engineVersion": artifact.get("engineVersion"),
            "revision": artifact.get("revision"),
            "kind": artifact.get("kind"),
            "artifactKey": artifact_key,
        },
        "decision": decision,
        "terminal": terminal,
        "gatewayCalls": matching_calls,
        "chapterExactMatch": True,
        "outlineUnchanged": True,
    }
    yield Scenario(
        name="legacy_langgraph_web_v1_round_trip",
        run_id=task_id,
        session_id=session_id,
        client_request_id=str(start_body["clientRequestId"]),
        provider_identity={"provider": "fake", "route": "legacy_langgraph"},
        database_facts=return_facts,
    )
