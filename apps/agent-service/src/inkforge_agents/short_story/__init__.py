"""中短篇专用写作流程的纯领域逻辑。"""

from .outline import (
    ShortOutlineFullSubmission,
    ShortOutlinePatchSubmission,
    SubmitShortStoryOutlineArgs,
    build_initial_short_outline,
    merge_short_outline_patch,
)

__all__ = [
    "ShortOutlineFullSubmission",
    "ShortOutlinePatchSubmission",
    "SubmitShortStoryOutlineArgs",
    "build_initial_short_outline",
    "merge_short_outline_patch",
]
