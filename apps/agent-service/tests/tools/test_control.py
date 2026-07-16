from __future__ import annotations

from inkforge_agents.tools.control import QualityReportArgs
from inkforge_contracts import ConsistencyQualityReport


def test_quality_tool_reuses_shared_report_contract() -> None:
    assert issubclass(QualityReportArgs, ConsistencyQualityReport)
    assert QualityReportArgs.model_fields.keys() == ConsistencyQualityReport.model_fields.keys()
