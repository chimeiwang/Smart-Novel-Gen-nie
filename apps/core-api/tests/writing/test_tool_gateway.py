import pytest
from inkforge_core.errors import ApiError
from inkforge_core.writing.tool_gateway import ToolGateway, ToolRequest


class FakeAuthorizer:
    def __init__(self) -> None:
        self.called = False

    async def require_binding(self, user_id: str, novel_id: str, task_id: str) -> None:
        self.called = True
        assert (user_id, novel_id, task_id) == ("user-1", "novel-1", "task-1")


@pytest.mark.asyncio
async def test_gateway_rejects_unauthorized_agent_before_handler() -> None:
    authorizer = FakeAuthorizer()
    handler_called = False

    async def handler(request: ToolRequest):
        nonlocal handler_called
        handler_called = True
        return {"content": "不应执行"}

    gateway = ToolGateway(authorizer)
    gateway.register("submit_quality_report", {"编辑"}, False, handler)

    with pytest.raises(ApiError) as error:
        await gateway.execute(
            ToolRequest(
                user_id="user-1",
                novel_id="novel-1",
                task_id="task-1",
                run_id="run-1",
                agent_id="写作",
                tool_name="submit_quality_report",
                arguments={},
            )
        )

    assert error.value.status_code == 403
    assert authorizer.called is False
    assert handler_called is False


@pytest.mark.asyncio
async def test_gateway_returns_complete_handler_result_after_binding_check() -> None:
    authorizer = FakeAuthorizer()
    complete = "完整结果" * 20_000

    async def handler(request: ToolRequest):
        assert request.arguments == {"query": "问题"}
        return {"content": complete}

    gateway = ToolGateway(authorizer)
    gateway.register("get_writing_context", {"写作"}, True, handler)

    result = await gateway.execute(
        ToolRequest(
            user_id="user-1",
            novel_id="novel-1",
            task_id="task-1",
            run_id="run-1",
            agent_id="写作",
            tool_name="get_writing_context",
            arguments={"query": "问题"},
        )
    )

    assert authorizer.called is True
    assert result["content"] == complete
