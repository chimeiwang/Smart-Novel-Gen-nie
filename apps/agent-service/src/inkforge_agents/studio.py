from __future__ import annotations

from typing import Any

from .graph.parent_graph import ParentGraphDependencies, build_parent_graph
from .operations.graph import OperationDependencies


class _UnavailableAgentExecutor:
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        del agent_id, state
        raise RuntimeError("Studio 尚未接入任务 15 的核心接口服务客户端")


class _UnavailableArtifactPort:
    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"Studio 草案端口尚未接入：{name}")


graph = build_parent_graph(
    ParentGraphDependencies(
        operation=OperationDependencies(
            agentExecutor=_UnavailableAgentExecutor(),
            artifacts=_UnavailableArtifactPort(),
        )
    )
)
