from __future__ import annotations

import pytest
from inkforge_contracts import (
    IntentAvailableOperation,
    IntentClarificationAnswer,
    IntentContext,
    IntentResolutionInput,
    IntentResolutionOutput,
    ProposedCommand,
)
from pydantic import ValidationError


def clarification():
    return {
        "decisionStepId": "decision-1",
        "prompt": "  需要规划还是写正文？\r\n请说明。  ",
        "userMessage": "  先规划。\r\n保留这些要求。  ",
    }


def available_operation(operation="plan_chapter"):
    return {
        "operation": operation,
        "description": "  为当前章生成待确认计划。  ",
        "targetType": "chapter",
        "scopeKind": "chapter",
    }


def context():
    return {
        "workflow": "long_serial",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "chapterTitle": "",
        "availableOperations": [available_operation()],
    }


def test_intent_input_preserves_complete_messages_and_order():
    instruction = "  全部要求😀\r\n" * 10_000
    first = clarification()
    second = first | {"decisionStepId": "decision-2", "userMessage": instruction}
    value = IntentResolutionInput.model_validate(
        {"userInstruction": instruction, "clarifications": [first, second]}
    )
    assert value.userInstruction == instruction
    assert value.model_dump()["clarifications"] == [first, second]
    assert IntentResolutionInput(userInstruction="完整要求").clarifications == []
    assert IntentClarificationAnswer.model_validate(first).model_dump() == first


@pytest.mark.parametrize("value", ["", " \r\n\ufeff\u0085\u3000", None, 1, True])
def test_intent_input_rejects_blank_or_non_string_messages(value):
    with pytest.raises(ValidationError):
        IntentResolutionInput.model_validate({"userInstruction": value})
    for field in ("prompt", "userMessage"):
        with pytest.raises(ValidationError):
            IntentClarificationAnswer.model_validate(clarification() | {field: value})


@pytest.mark.parametrize(
    "answers",
    [None, {}, [clarification(), clarification()], [clarification()] * 3],
)
def test_intent_input_rejects_invalid_or_duplicate_clarifications(answers):
    with pytest.raises(ValidationError):
        IntentResolutionInput.model_validate(
            {"userInstruction": "规划", "clarifications": answers}
        )


def test_intent_context_has_no_shared_operation_catalog_or_extra_workspace():
    value = context()
    assert IntentContext.model_validate(value).model_dump() == value
    future = available_operation("future_operation")
    assert IntentAvailableOperation.model_validate(future).operation == "future_operation"
    for field in ("content", "selectedAgents", "schemaVersion"):
        with pytest.raises(ValidationError):
            IntentContext.model_validate(value | {field: "额外内容"})
    for field in value:
        with pytest.raises(ValidationError):
            IntentContext.model_validate({key: val for key, val in value.items() if key != field})
    with pytest.raises(ValidationError):
        IntentResolutionInput.model_validate({"userInstruction": "规划", "targetWordCount": 4000})


@pytest.mark.parametrize(
    "changed",
    [
        {"workflow": "short_medium"},
        {"chapterTitle": None},
        {"availableOperations": []},
        {"availableOperations": [available_operation()] * 2},
        {"availableOperations": [available_operation(f"operation_{index}") for index in range(4)]},
        {"availableOperations": None},
    ],
)
def test_intent_context_rejects_inconsistent_authorized_shape(changed):
    with pytest.raises(ValidationError):
        IntentContext.model_validate(context() | changed)


@pytest.mark.parametrize(
    "changed",
    [
        {"operation": "INVALID"},
        {"description": " \r\n\ufeff"},
        {"targetType": "novel"},
        {"scopeKind": "novel"},
        {"targetId": "chapter-1"},
    ],
)
def test_intent_available_operation_is_strict(changed):
    with pytest.raises(ValidationError):
        IntentAvailableOperation.model_validate(available_operation() | changed)


def test_intent_output_preserves_clarification_when_converted_to_base_command():
    value = {
        "confidence": 0.3,
        "clarification": {"code": "operation_uncertain", "prompt": clarification()["prompt"]},
    }
    output = IntentResolutionOutput.model_validate(value)
    command = ProposedCommand.model_validate(output.model_dump(mode="json"))
    assert command.clarification.prompt == value["clarification"]["prompt"]
    assert command.model_dump(mode="json") == output.model_dump(mode="json")
    resolved = IntentResolutionOutput.model_validate(
        {"workflow": "long_serial", "operation": "plan_chapter", "confidence": 0.9}
    )
    assert resolved.arguments == {}
    assert resolved.targetId is None


@pytest.mark.parametrize(
    "changed",
    [
        {"targetType": "chapter"},
        {"targetId": "chapter-1"},
        {"scopeKind": "chapter"},
        {"arguments": {"targetWordCount": 4000}},
        {"arguments": None},
        {"workflow": "short_medium"},
        {"operation": None},
        {"confidence": True},
        {"confidence": "0.9"},
        {"confidence": 1.1},
        {"clarification": {"code": "uncertain", "prompt": "请选择"}},
        {"userInstruction": "模型新增要求"},
    ],
)
def test_intent_output_rejects_identity_arguments_and_ambiguous_result(changed):
    with pytest.raises(ValidationError):
        IntentResolutionOutput.model_validate(
            {"workflow": "long_serial", "operation": "plan_chapter", "confidence": 0.9} | changed
        )


def test_intent_schema_has_closed_objects_and_no_arbitrary_message_length_limit():
    schema = IntentResolutionInput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "maxLength" not in schema["properties"]["userInstruction"]
    answer = schema["$defs"]["IntentClarificationAnswer"]["properties"]
    assert "maxLength" not in answer["userMessage"]
    assert schema["properties"]["clarifications"]["maxItems"] == 2
    output = IntentResolutionOutput.model_json_schema()
    assert output["additionalProperties"] is False
    for field in ("targetType", "targetId", "scopeKind"):
        assert output["properties"][field]["type"] == "null"
    assert output["properties"]["arguments"]["maxProperties"] == 0
