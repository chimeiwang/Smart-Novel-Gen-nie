from __future__ import annotations

from typing import Protocol

from .human_workflow_log import HumanWorkflowLog


class ModelContext(Protocol):
    runId: str
    agentId: str


class WorkflowModelObserver:
    def __init__(self, workflow_log: HumanWorkflowLog) -> None:
        self._workflow_log = workflow_log

    def record_model_call(
        self,
        context: ModelContext,
        messages: list[dict[str, str]],
        output: str,
    ) -> None:
        self._workflow_log.record_model_call(
            context.runId,
            context.agentId,
            messages,
            output,
        )
