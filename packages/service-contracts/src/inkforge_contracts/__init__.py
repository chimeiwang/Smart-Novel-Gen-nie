"""InkForge Python 服务间的共享协议。"""

from .events import AgentEvent, CheckpointCallback, RunCompletionCallback, RunFailureCallback
from .identity import CoreAgentId
from .jobs import AgentJobAccepted, AgentJobCancelRequest, AgentJobRequest, AgentJobStatus
from .jwt_claims import ServiceJwtClaims, ServiceScope
from .quality import (
    ConsistencyDimension,
    ConsistencyIssue,
    ConsistencyQualityReport,
    ConsistencyScores,
)
from .runs import CreativeOperationKind, RunAccepted, RunRequest, RunStatusResponse
from .short_story import (
    ShortStoryAnchors,
    ShortStoryDraftMetadata,
    ShortStoryOutlineDraft,
    ShortStoryOutlineSection,
    render_short_story_outline,
)
from .tools import ToolCallRequest, ToolCallResult
from .version import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "AgentEvent",
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
    "CreativeOperationKind",
    "RunAccepted",
    "RunCompletionCallback",
    "RunFailureCallback",
    "RunRequest",
    "RunStatusResponse",
    "ShortStoryAnchors",
    "ShortStoryDraftMetadata",
    "ShortStoryOutlineDraft",
    "ShortStoryOutlineSection",
    "ServiceJwtClaims",
    "ServiceScope",
    "ToolCallRequest",
    "ToolCallResult",
    "render_short_story_outline",
]
