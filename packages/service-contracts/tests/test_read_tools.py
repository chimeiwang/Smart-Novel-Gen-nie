import jsonschema_rs
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


@pytest.mark.parametrize(
    ("arguments", "valid"),
    [
        ({}, False),
        ({"node_id": None}, False),
        ({"node_id": ""}, False),
        ({"node_id": "节点-1"}, True),
        ({"node_title": "第一幕"}, True),
        ({"node_id": None, "node_title": "第一幕"}, True),
        ({"node_id": "节点-1", "node_title": "第一幕"}, True),
    ],
)
def test_大纲节点定位的模型_schema_与本地校验一致(
    arguments: dict[str, object], valid: bool
) -> None:
    model = READ_TOOL_ARGUMENT_MODELS["get_outline_node"]
    schema = model.model_json_schema()

    assert jsonschema_rs.is_valid(schema, arguments) is valid
    try:
        model.model_validate(arguments)
    except ValidationError as error:
        assert not valid
        if not arguments or arguments == {"node_id": None}:
            assert error.errors()[0]["type"] == "outline_locator_required"
    else:
        assert valid
