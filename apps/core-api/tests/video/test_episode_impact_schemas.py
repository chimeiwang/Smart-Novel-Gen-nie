from __future__ import annotations

import pytest
from inkforge_core.video.episodes.impact_schemas import DecideVideoImpactReviewRequest
from pydantic import ValidationError


def test_impact_decisions_reject_duplicate_items() -> None:
    with pytest.raises(ValidationError, match="同一影响项不能重复决定"):
        DecideVideoImpactReviewRequest.model_validate(
            {
                "clientRequestId": "impact-request-0001",
                "expectedRevision": 1,
                "decisions": [
                    {
                        "itemId": "dependency-1",
                        "action": "keep_existing",
                        "note": "已确认是独立时间线",
                    },
                    {"itemId": "dependency-1", "action": "defer", "note": "稍后处理"},
                ],
            }
        )


def test_impact_decisions_use_explicit_supported_action() -> None:
    request = DecideVideoImpactReviewRequest.model_validate(
        {
            "clientRequestId": "impact-request-0002",
            "expectedRevision": 3,
            "decisions": [
                {
                    "itemId": "dependency-1",
                    "action": "revise_target",
                    "note": "第二集改为追信",
                }
            ],
        }
    )

    assert request.decisions[0].action == "revise_target"
