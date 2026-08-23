from __future__ import annotations

from typing import Literal

ModelExecutionStage = Literal[
    "primary",
    "reviewer",
    "reviser",
    "quality",
    "protocol_repair",
]


class ModelExecutionError(RuntimeError):
    """模型执行期间可供队列和工作流读取的类型化错误。"""

    def __init__(
        self,
        *,
        code: str,
        category: str,
        stage: ModelExecutionStage,
        retryable: bool,
        safeToRetry: bool,
        publicMessage: str,
        requestId: str | None = None,
        usageReported: bool = False,
    ) -> None:
        if safeToRetry and not retryable:
            raise ValueError("safeToRetry=true 必须同时 retryable=true")
        super().__init__(publicMessage)
        self.code = code
        self.category = category
        self.stage = stage
        self.retryable = retryable
        self.safeToRetry = safeToRetry
        self.publicMessage = publicMessage
        self.requestId = requestId
        self.usageReported = usageReported


class ReviewExecutionError(ModelExecutionError):
    """复审阶段错误，避免被当成草案内容结论。"""


class ProviderTransportError(RuntimeError):
    """供应商传输边界错误，保留是否可以安全重发的独立语义。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        safe_to_retry: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.safe_to_retry = safe_to_retry


class UnknownJobExecutionError(RuntimeError):
    """无法分类的任务执行错误，不得降级为业务评审结论。"""
