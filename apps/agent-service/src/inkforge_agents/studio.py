from __future__ import annotations

from typing import Any

from .graph.parent_graph import ParentGraphDependencies, build_parent_graph
from .operations.contracts import CreativeOperationKind
from .operations.graph import OperationDependencies
from .runtime.execution import AgentExecutionMode


class _UnavailableAgentExecutor:
    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: AgentExecutionMode,
        operation_kind: CreativeOperationKind,
    ) -> dict[str, Any]:
        del agent_id, state, execution_mode, operation_kind
        raise RuntimeError("Studio 结构调试入口不执行真实模型任务")


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
