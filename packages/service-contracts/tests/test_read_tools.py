import pytest
from inkforge_contracts.read_tools import READ_TOOL_ARGUMENT_MODELS, READ_TOOL_NAMES
from pydantic import ValidationError


def test_read_tool_contract_contains_all_agent_read_tools() -> None:
    assert len(READ_TOOL_NAMES) == 26
    assert set(READ_TOOL_NAMES) == set(READ_TOOL_ARGUMENT_MODELS)
    assert "get_review_artifact" in READ_TOOL_NAMES


def test_review_artifact_contract_uses_snake_case_parameter() -> None:
    model = READ_TOOL_ARGUMENT_MODELS["get_review_artifact"]

    assert model.model_validate({"artifact_id": "artifact-1"}).model_dump() == {
        "artifact_id": "artifact-1"
    }
    with pytest.raises(ValidationError):
        model.model_validate({"artifactId": "artifact-1"})


def test_最近章节参数接受二十章() -> None:
    model = READ_TOOL_ARGUMENT_MODELS["get_recent_chapters"]

    assert model.model_validate({"count": 20}).model_dump() == {"count": 20}


def test_最近章节参数拒绝二十一章() -> None:
    model = READ_TOOL_ARGUMENT_MODELS["get_recent_chapters"]

    with pytest.raises(ValidationError):
        model.model_validate({"count": 21})
