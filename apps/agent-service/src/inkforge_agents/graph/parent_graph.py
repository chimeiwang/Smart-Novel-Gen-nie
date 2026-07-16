from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..operations.graph import OperationDependencies, build_operation_graph
from ..operations.router import OperationClassifier, route_creative_operation
from .state import GraphState


@dataclass(frozen=True, slots=True)
class ParentGraphDependencies:
    operation: OperationDependencies
    classifier: OperationClassifier | None = None


def build_parent_graph(
    dependencies: ParentGraphDependencies,
    *,
    checkpointer: Any | None = None,
) -> Any:
    operation_graph = build_operation_graph(dependencies.operation)

    async def init_session(state: GraphState) -> dict[str, Any]:
        routed = await route_creative_operation(
            state["userMessage"],
            dependencies.classifier,
        )
        return {
            "currentOperation": routed.operation.model_dump(),
            "activeAgent": routed.operation.primaryAgent,
            "operationStep": "classify_operation",
            "operationStage": "识别创作操作",
        }

    builder = StateGraph(GraphState)
    builder.add_node("initSession", init_session)
    builder.add_node("operationWorkflow", operation_graph)
    builder.add_edge(START, "initSession")
    builder.add_edge("initSession", "operationWorkflow")
    builder.add_edge("operationWorkflow", END)
    return builder.compile(checkpointer=checkpointer)
