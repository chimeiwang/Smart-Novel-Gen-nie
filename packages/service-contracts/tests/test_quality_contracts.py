from __future__ import annotations

import pytest
from inkforge_contracts import ConsistencyQualityReport
from pydantic import ValidationError


def valid_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "scores": {
            "characterConsistency": 81.0,
            "worldRuleConsistency": 82.0,
            "timelineConsistency": 83.0,
            "causalityConsistency": 84.0,
            "foreshadowingConsistency": 88.0,
        },
        "qualityGate": "revise",
        "issues": [
            {
                "dimension": "timeline",
                "severity": "warning",
                "message": "时间顺序需要核对",
                "evidence": "第二幕发生时间早于第一幕结尾",
                "location": "第二幕开头",
                "suggestion": "统一两处日期",
            }
        ],
        "report": "完整一致性报告",
        "rewriteBrief": "修正时间线后复核",
    }
    report.update(overrides)
    return report


@pytest.mark.parametrize(
    "scores",
    [
        {
            "characterConsistency": 81.0,
            "worldRuleConsistency": 82.0,
            "timelineConsistency": 83.0,
            "causalityConsistency": 84.0,
        },
        {
            "characterConsistency": 81.0,
            "worldRuleConsistency": 82.0,
            "timelineConsistency": 83.0,
            "causalityConsistency": 84.0,
            "foreshadowingConsistency": 88.0,
            "overall": 84.0,
        },
    ],
)
def test_quality_report_rejects_missing_or_extra_scores(
    scores: dict[str, float],
) -> None:
    with pytest.raises(ValidationError):
        ConsistencyQualityReport.model_validate(valid_report(scores=scores))


@pytest.mark.parametrize("score", [-0.1, 100.1])
def test_quality_report_rejects_out_of_range_score(score: float) -> None:
    scores = dict(valid_report()["scores"])  # type: ignore[arg-type]
    scores["timelineConsistency"] = score

    with pytest.raises(ValidationError):
        ConsistencyQualityReport.model_validate(valid_report(scores=scores))


@pytest.mark.parametrize("report", ["", "   \r\n"])
def test_quality_report_requires_non_blank_report(report: str) -> None:
    with pytest.raises(ValidationError):
        ConsistencyQualityReport.model_validate(valid_report(report=report))


def test_quality_report_preserves_non_blank_content_exactly() -> None:
    report = "  完整一致性报告\n"

    validated = ConsistencyQualityReport.model_validate(valid_report(report=report))

    assert validated.report == report


def test_quality_report_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ConsistencyQualityReport.model_validate(valid_report(unexpected=True))


@pytest.mark.parametrize(
    "issue",
    [
        {
            "dimension": "commercial",
            "severity": "warning",
            "message": "错误维度",
            "evidence": "证据",
            "suggestion": "建议",
        },
        {
            "dimension": "character",
            "severity": "info",
            "message": "错误级别",
            "evidence": "证据",
            "suggestion": "建议",
        },
        {
            "dimension": "character",
            "severity": "error",
            "message": "",
            "evidence": "证据",
            "suggestion": "建议",
        },
        {
            "dimension": "character",
            "severity": "error",
            "message": "冲突",
            "evidence": "证据",
            "suggestion": "建议",
            "extra": "越权字段",
        },
    ],
)
def test_quality_report_rejects_invalid_issue_fields(issue: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsistencyQualityReport.model_validate(valid_report(issues=[issue]))
