"""InkForge Python 服务间的共享协议。"""

from .events import AgentEvent, CheckpointCallback, RunCompletionCallback, RunFailureCallback
from .identity import CoreAgentId
from .jobs import (
    AgentJobAccepted,
    AgentJobCancelRequest,
    AgentJobRequest,
    AgentJobStatus,
    ApprovedShortOutlineSource,
    ShortOutlineInspirationSource,
    WritingJobPayload,
)
from .jwt_claims import ServiceJwtClaims, ServiceScope
from .quality import (
    ConsistencyDimension,
    ConsistencyIssue,
    ConsistencyQualityReport,
    ConsistencyScores,
)
from .runs import (
    CreativeOperationKind,
    RunAccepted,
    RunRequest,
    RunStatusResponse,
    WritingWorkflowKind,
)
from .short_story import (
    SHORT_STORY_IGNORED_TEXT_CHARACTERS,
    ShortStoryAnchors,
    ShortStoryChapterDraft,
    ShortStoryDraftMetadata,
    ShortStoryOutlineDraft,
    ShortStoryOutlineSection,
    canonical_short_outline_hash,
    count_short_story_text_length,
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
    "ApprovedShortOutlineSource",
    "CreativeOperationKind",
    "RunAccepted",
    "RunCompletionCallback",
    "RunFailureCallback",
    "RunRequest",
    "RunStatusResponse",
    "SHORT_STORY_IGNORED_TEXT_CHARACTERS",
    "ShortOutlineInspirationSource",
    "ShortStoryAnchors",
    "ShortStoryChapterDraft",
    "ShortStoryDraftMetadata",
    "ShortStoryOutlineDraft",
    "ShortStoryOutlineSection",
    "ServiceJwtClaims",
    "ServiceScope",
    "ToolCallRequest",
    "ToolCallResult",
    "WritingJobPayload",
    "WritingWorkflowKind",
    "canonical_short_outline_hash",
    "count_short_story_text_length",
    "render_short_story_outline",
]
