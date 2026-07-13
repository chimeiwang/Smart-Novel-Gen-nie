from typing import Any

import pytest
from inkforge_contracts.read_tools import READ_TOOL_NAMES
from inkforge_core.errors import ApiError
from inkforge_core.writing.read_tools import register_read_tools
from inkforge_core.writing.tool_gateway import ToolGateway, ToolRequest


class FakeAuthorizer:
    async def require_binding(self, user_id: str, novel_id: str, task_id: str) -> None:
        assert (user_id, novel_id, task_id) == ("user-1", "novel-1", "task-1")


class FakeReadToolService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, request: ToolRequest) -> dict[str, Any]:
        self.calls.append((request.tool_name, request.arguments))
        return {"tool": request.tool_name, "arguments": request.arguments}


def request(tool_name: str, arguments: dict[str, Any]) -> ToolRequest:
    return ToolRequest(
        user_id="user-1",
        novel_id="novel-1",
        task_id="task-1",
        run_id="run-1",
        agent_id="写作",
        tool_name=tool_name,
        arguments=arguments,
    )


def test_registers_every_shared_read_tool() -> None:
    gateway = ToolGateway(FakeAuthorizer())
    register_read_tools(gateway, FakeReadToolService())

    assert gateway.registered_names == frozenset(READ_TOOL_NAMES)
    assert all(gateway.is_read_only(name) for name in READ_TOOL_NAMES)


@pytest.mark.asyncio
async def test_validates_and_forwards_shared_arguments() -> None:
    service = FakeReadToolService()
    gateway = ToolGateway(FakeAuthorizer())
    register_read_tools(gateway, service)

    result = await gateway.execute(request("get_review_artifact", {"artifact_id": "artifact-1"}))

    assert result["arguments"] == {"artifact_id": "artifact-1"}
    assert service.calls == [("get_review_artifact", {"artifact_id": "artifact-1"})]


@pytest.mark.asyncio
async def test_rejects_legacy_camel_case_artifact_parameter() -> None:
    gateway = ToolGateway(FakeAuthorizer())
    register_read_tools(gateway, FakeReadToolService())

    with pytest.raises(ApiError) as error:
        await gateway.execute(request("get_review_artifact", {"artifactId": "artifact-1"}))

    assert error.value.status_code == 422
    assert error.value.code == "TOOL_ARGUMENTS_INVALID"


@pytest.mark.asyncio
async def test_semantic_search_accepts_internal_query_embedding() -> None:
    service = FakeReadToolService()
    gateway = ToolGateway(FakeAuthorizer())
    register_read_tools(gateway, service)

    await gateway.execute(
        request(
            "semantic_search_references",
            {"query": "文字", "topK": 5, "query_embedding": [0.1, 0.2]},
        )
    )

    assert service.calls == [
        (
            "semantic_search_references",
            {"query": "文字", "topK": 5, "query_embedding": [0.1, 0.2]},
        )
    ]
