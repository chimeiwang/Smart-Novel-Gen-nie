from inkforge_core.app import create_app
from inkforge_core.writing.schemas import WritingRunV2Response


def test_short_medium_v2_result_projection_preserves_exact_candidate_and_report():
    candidate = WritingRunV2Response.model_construct(candidateVersionId="candidate-1")
    assert candidate.model_dump(mode="json")["candidateVersionId"] == "candidate-1"
    report = {"text": "  完整检查😀\r\n" * 10_001 + "尾部🚀"}
    checked = WritingRunV2Response.model_construct(checkReport=report)
    assert checked.model_dump(mode="json")["checkReport"] == report


def test_short_medium_v2_optional_results_do_not_change_other_workflow_payloads():
    empty = WritingRunV2Response.model_construct()
    assert "candidateVersionId" not in empty.model_dump(mode="json")
    assert "checkReport" not in empty.model_dump(mode="json")
    explicit_null = WritingRunV2Response.model_construct(
        candidateVersionId=None, checkReport=None,
    )
    assert "candidateVersionId" not in explicit_null.model_dump(mode="json")
    assert "checkReport" not in explicit_null.model_dump(mode="json")


def test_short_medium_v2_result_fields_are_exported_as_optional_public_contracts():
    schema = create_app(testing=True).openapi()["components"]["schemas"][
        "WritingRunV2Response"
    ]
    for field in ("candidateVersionId", "checkReport"):
        assert field in schema["properties"]
        assert field not in schema["required"]
