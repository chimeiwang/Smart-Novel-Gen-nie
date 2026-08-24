from __future__ import annotations

from ..runtime.model_runtime import ModelCallFailureLogRecord, ModelCallLogRecord
from .human_workflow_log import HumanWorkflowLog


class WorkflowModelObserver:
    def __init__(self, workflow_log: HumanWorkflowLog) -> None:
        self._workflow_log = workflow_log

    def record_model_call(self, record: ModelCallLogRecord) -> None:
        self._workflow_log.record_model_call(record)

    def record_model_failure(self, record: ModelCallFailureLogRecord) -> None:
        self._workflow_log.record_model_failure(record)
