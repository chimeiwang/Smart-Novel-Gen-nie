from __future__ import annotations

import math
from typing import Any, Protocol

from inkforge_contracts.read_tools import READ_TOOL_ARGUMENT_MODELS
from pydantic import BaseModel, ValidationError

from ..errors import ApiError
from .tool_gateway import ToolGateway, ToolRequest

ALL_AGENT_IDS = {"设定", "剧情", "写作", "校验", "编辑"}


class ReadToolServicePort(Protocol):
    async def execute(self, request: ToolRequest) -> dict[str, Any]: ...


def register_read_tools(gateway: ToolGateway, service: ReadToolServicePort) -> None:
    for name, arguments_model in READ_TOOL_ARGUMENT_MODELS.items():

        async def handler(
            request: ToolRequest,
            *,
            model: type[BaseModel] = arguments_model,
        ) -> dict[str, Any]:
            raw_arguments = dict(request.arguments)
            query_embedding = raw_arguments.pop("query_embedding", None)
            try:
                arguments = model.model_validate(raw_arguments).model_dump(exclude_none=True)
                if query_embedding is not None:
                    if request.tool_name != "semantic_search_references":
                        raise ValueError("只有语义检索工具允许内部查询向量")
                    arguments["query_embedding"] = _validate_embedding(query_embedding)
            except (ValidationError, ValueError) as exc:
                raise ApiError(
                    status_code=422,
                    code="TOOL_ARGUMENTS_INVALID",
                    message="智能体工具参数无效",
                ) from exc
            validated = ToolRequest(
                user_id=request.user_id,
                novel_id=request.novel_id,
                task_id=request.task_id,
                run_id=request.run_id,
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                arguments=arguments,
            )
            return await service.execute(validated)

        gateway.register(name, ALL_AGENT_IDS, True, handler)


def _validate_embedding(value: object) -> list[float]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 4096
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in value
        )
    ):
        raise ValueError("查询向量格式无效")
    return [float(item) for item in value]
