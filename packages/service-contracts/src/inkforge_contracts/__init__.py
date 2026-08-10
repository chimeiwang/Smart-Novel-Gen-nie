"""InkForge Python 服务间的共享协议。"""

from .events import (
    AgentEvent,
    CallbackReceipt,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from .identity import CoreAgentId
from .jobs import AgentJobAccepted, AgentJobCancelRequest, AgentJobRequest, AgentJobStatus
from .jwt_claims import ServiceJwtClaims, ServiceScope
from .long_serial import (
    LONG_SERIAL_RUN_PAYLOAD_ADAPTER,
    PUBLIC_LONG_SERIAL_OPERATIONS,
    AbsenceSentinel,
    ChapterRangeScope,
    ChapterScope,
    ChapterTarget,
    LongSerialResumeInput,
    LongSerialRunBase,
    LongSerialRunPayload,
    LongSerialScope,
    NovelScope,
    OutlineNodeScope,
    ResumeLongSerialRunPayload,
    SelectionSnapshot,
    SelectionSourceSnapshot,
    SelectionTarget,
    SourceBinding,
    StartLongSerialRunPayload,
)
from .operations import (
    CreativeOperationKind,
    ExecutableCreativeOperationKind,
    HistoricalCreativeOperationKind,
    PublicOperationDefinition,
)
from .quality import (
    ConsistencyDimension,
    ConsistencyIssue,
    ConsistencyQualityReport,
    ConsistencyScores,
)
from .runs import RunAccepted, RunRequest, RunStatusResponse
from .short_medium import (
    ShortMediumCheckResult,
    ShortMediumDocumentResult,
    ShortMediumDocumentType,
    ShortMediumOperation,
    ShortMediumReplacementResult,
    ShortMediumRunPayload,
)
from .tools import ToolCallRequest, ToolCallResult
from .version import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "AgentEvent",
    "CallbackReceipt",
    "CheckpointCallback",
    "ConsistencyDimension",
    "ConsistencyIssue",
    "ConsistencyQualityReport",
    "ConsistencyScores",
    "CoreAgentId",
    "AgentJobAccepted",
    "AgentJobCancelRequest",
    "AgentJobRequest",
    "AgentJobStatus",
    "AbsenceSentinel",
    "ChapterRangeScope",
    "ChapterScope",
    "ChapterTarget",
    "CreativeOperationKind",
    "ExecutableCreativeOperationKind",
    "HistoricalCreativeOperationKind",
    "LONG_SERIAL_RUN_PAYLOAD_ADAPTER",
    "LongSerialResumeInput",
    "LongSerialRunBase",
    "LongSerialRunPayload",
    "LongSerialScope",
    "NovelScope",
    "OutlineNodeScope",
    "PUBLIC_LONG_SERIAL_OPERATIONS",
    "PublicOperationDefinition",
    "ResumeLongSerialRunPayload",
    "RunAccepted",
    "RunCompletionCallback",
    "RunFailureCallback",
    "RunRequest",
    "RunStatusResponse",
    "SourceBinding",
    "SelectionTarget",
    "SelectionSnapshot",
    "SelectionSourceSnapshot",
    "StartLongSerialRunPayload",
    "ShortMediumCheckResult",
    "ShortMediumDocumentResult",
    "ShortMediumDocumentType",
    "ShortMediumOperation",
    "ShortMediumReplacementResult",
    "ShortMediumRunPayload",
    "ServiceJwtClaims",
    "ServiceScope",
    "ToolCallRequest",
    "ToolCallResult",
]
