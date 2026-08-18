from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, NonNegativeInt, model_validator

ModelFinishReason = Literal[
    "stop",
    "tool_calls",
    "length",
    "content_filter",
    "unknown",
]
ModelThinkingMode = Literal["provider_default", "disabled"]
ModelStructuredOutputRoute = Literal[
    "responses_json_schema_v1",
    "chat_json_output_v1",
]
ModelStructuredOutputDiagnosticCode = Literal[
    "json_decode_error",
    "schema_violation",
    "not_object",
    "empty_output",
    "multiple_text_outputs",
    "response_incomplete",
    "response_failed",
    "unexpected_output",
]
ModelInvalidToolCallCode = Literal[
    "json_decode_error",
    "missing_tool_name",
    "provider_strict_schema_violation",
    "unknown_invalid_tool_call",
]
ModelToolRecoveryCode = Literal["append_container_closers"]
ProviderTransportErrorCode = Literal[
    "http_error",
    "connection_error",
    "timeout_error",
]


class ProviderTransportError(RuntimeError):
    """不携带供应商响应正文、请求正文或底层 SDK 异常的可重试传输错误。"""

    retryable = True

    def __init__(
        self,
        *,
        code: ProviderTransportErrorCode,
        statusCode: int | None,
        requestId: str | None,
    ) -> None:
        self.code = code
        self.statusCode = statusCode
        self.requestId = requestId
        super().__init__(
            f"供应商传输失败(code={code},statusCode={statusCode},requestId={requestId})"
        )

    def __repr__(self) -> str:
        """显式限制 repr 字段，避免调试器重新展示底层 SDK 响应正文。"""

        return (
            "ProviderTransportError("
            f"code={self.code!r}, statusCode={self.statusCode!r}, "
            f"requestId={self.requestId!r}, retryable=True)"
        )


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, JsonValue]


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_calls: list[ModelToolCall] = Field(default_factory=list, alias="toolCalls")


class ModelTool(BaseModel):
    """模型工具声明；strict 只在供应商明确支持时启用。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, JsonValue]
    strict: bool = False


class ModelStructuredOutputRequest(BaseModel):
    """供应商原生结构化输出请求，不借用业务工具调用通道。"""

    model_config = ConfigDict(extra="forbid")

    route: ModelStructuredOutputRoute
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    jsonSchema: dict[str, JsonValue]


class ModelStructuredOutputDiagnostic(BaseModel):
    """不包含供应商正文、字段值或未知字段名的结构化输出诊断。"""

    model_config = ConfigDict(extra="forbid")

    code: ModelStructuredOutputDiagnosticCode
    jsonPointer: str
    keyword: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_$.-]+$")


class ModelTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage]
    tools: list[ModelTool]
    maxOutputTokens: int = Field(gt=0)
    # 默认不干预供应商能力；只有确定不需要长链路推理的 strict 任务才显式关闭。
    thinkingMode: ModelThinkingMode = "provider_default"
    # strict 结构任务可指定唯一必调函数，Provider 负责下发 named tool_choice。
    requiredToolName: str | None = None
    # 默认保持供应商并行能力；单结构包任务必须显式关闭。
    parallelToolCalls: bool = True
    # 结构化文本输出与工具通道互斥，避免同一响应同时承担两种控制协议。
    structuredOutput: ModelStructuredOutputRequest | None = None

    @model_validator(mode="after")
    def validate_required_tool(self) -> ModelTurnRequest:
        """必调函数必须存在且工具名不能重复，避免传输层选择歧义。"""

        tool_names = [tool.name for tool in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("模型工具名称不能重复")
        if self.structuredOutput is not None and self.tools:
            raise ValueError("structuredOutput 不能与 tools 同时使用")
        if self.structuredOutput is not None and self.requiredToolName is not None:
            raise ValueError("structuredOutput 不能与 requiredToolName 同时使用")
        if self.requiredToolName is not None and self.requiredToolName not in tool_names:
            raise ValueError("requiredToolName 必须引用当前请求中的工具")
        return self


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promptTokens: NonNegativeInt
    cachedTokens: NonNegativeInt = 0
    completionTokens: NonNegativeInt
    totalTokens: NonNegativeInt


class ModelTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    toolCalls: list[ModelToolCall]
    # 不保存无效 arguments/error 正文，只暴露安全派生信息供稳定诊断。
    invalidToolCallCount: NonNegativeInt = 0
    invalidToolCallNames: list[str] = Field(default_factory=list)
    invalidToolCallCodes: list[ModelInvalidToolCallCode] = Field(default_factory=list)
    invalidToolCallArgumentCharacterCounts: list[NonNegativeInt] = Field(default_factory=list)
    # 恢复审计只保存方法与追加容器数，绝不保存模型的原始 arguments。
    recoveredToolCallCount: NonNegativeInt = 0
    recoveredToolCallCodes: list[ModelToolRecoveryCode] = Field(default_factory=list)
    recoveredToolCallAppendedContainerCounts: list[NonNegativeInt] = Field(default_factory=list)
    # 只有已解析且通过调用方原始 JSON Schema 复验的对象才能进入结果。
    structuredOutput: dict[str, JsonValue] | None = None
    structuredOutputDiagnostic: ModelStructuredOutputDiagnostic | None = None
    usage: ModelUsage
    finishReason: ModelFinishReason
    rawFinishReason: str | None = None
    # 真实 Provider 按 Runtime 最终授权后的请求填写，错误诊断不得再使用配置上限冒充。
    effectiveMaxOutputTokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_invalid_tool_call_diagnostics(self) -> ModelTurnResult:
        """平行诊断数组必须逐项对齐，防止错误文本错配工具调用。"""

        diagnostic_lengths = {
            len(self.invalidToolCallNames),
            len(self.invalidToolCallCodes),
            len(self.invalidToolCallArgumentCharacterCounts),
        }
        if diagnostic_lengths != {self.invalidToolCallCount}:
            raise ValueError("无效工具调用诊断数量必须与 invalidToolCallCount 一致")
        recovery_lengths = {
            len(self.recoveredToolCallCodes),
            len(self.recoveredToolCallAppendedContainerCounts),
        }
        if recovery_lengths != {self.recoveredToolCallCount}:
            raise ValueError("工具调用恢复审计数量必须与 recoveredToolCallCount 一致")
        if self.recoveredToolCallCount > len(self.toolCalls):
            raise ValueError("恢复工具调用数量不能超过有效工具调用数量")
        if self.structuredOutput is not None and self.structuredOutputDiagnostic is not None:
            raise ValueError("结构化输出与失败诊断不能同时存在")
        if self.structuredOutput is not None or self.structuredOutputDiagnostic is not None:
            if self.content:
                raise ValueError("结构化输出结果不能保留可见正文")
            if self.toolCalls:
                raise ValueError("结构化输出结果不能包含工具调用")
        return self


class ModelProvider(Protocol):
    billable: bool
    provider_name: str
    model_name: str

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult: ...
