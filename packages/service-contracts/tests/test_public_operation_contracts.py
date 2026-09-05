from __future__ import annotations

import pytest
from inkforge_contracts.long_serial import PUBLIC_LONG_SERIAL_OPERATIONS
from inkforge_contracts.operations import PublicOperationDefinition
from pydantic import ValidationError


def test_public_long_serial_operations_are_exact() -> None:
    assert {
        key: value.model_dump()
        for key, value in PUBLIC_LONG_SERIAL_OPERATIONS.items()
    } == {
        **{
            operation: {
                "operation": operation,
                "workflow": "long_serial",
                "targetKind": "chapter",
                "allowedScopeKinds": scopes,
                "mutating": True,
                "principalAgent": agent,
                "reviewers": (reviewer,),
                "artifactKind": "agent_updates",
            }
            for operation, scopes, agent, reviewer in (
                ("create_lore", ("novel",), "设定", "校验"),
                ("revise_lore", ("novel",), "设定", "校验"),
                ("create_outline", ("novel",), "剧情", "编辑"),
                ("revise_outline", ("novel", "outline_node"), "剧情", "编辑"),
                ("manage_foreshadowing", ("novel", "chapter"), "剧情", "校验"),
            )
        },
        "answer_question": {
            "operation": "answer_question",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": False,
            "principalAgent": "编辑",
            "reviewers": (),
            "artifactKind": None,
        },
        "plan_chapter": {
            "operation": "plan_chapter",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": True,
            "principalAgent": "剧情",
            "reviewers": ("编辑",),
            "artifactKind": "beat_plan",
        },
        "write_chapter": {
            "operation": "write_chapter",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": True,
            "principalAgent": "写作",
            "reviewers": ("校验", "编辑"),
            "artifactKind": "chapter_draft",
        },
        "rewrite_scene": {
            "operation": "rewrite_scene",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": True,
            "principalAgent": "写作",
            "reviewers": ("校验", "编辑"),
            "artifactKind": "chapter_draft",
        },
        "rewrite_chapter_selection": {
            "operation": "rewrite_chapter_selection",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": True,
            "principalAgent": "写作",
            "reviewers": ("校验", "编辑"),
            "artifactKind": "chapter_draft",
        },
            "rewrite_outline_selection": {
                "operation": "rewrite_outline_selection",
                "workflow": "long_serial",
                "targetKind": "chapter",
                "allowedScopeKinds": ("novel", "outline_node"),
            "mutating": True,
            "principalAgent": "剧情",
            "reviewers": ("编辑",),
            "artifactKind": "outline_draft",
        },
        "review_chapter": {
            "operation": "review_chapter",
            "workflow": "long_serial",
            "targetKind": "chapter",
            "allowedScopeKinds": ("chapter",),
            "mutating": False,
            "principalAgent": "编辑",
            "reviewers": (),
            "artifactKind": None,
        },
    }


def test_public_operation_definition_is_strict() -> None:
    with pytest.raises(ValidationError):
        PublicOperationDefinition.model_validate(
            {
                **PUBLIC_LONG_SERIAL_OPERATIONS["plan_chapter"].model_dump(),
                "toolNames": ["write_chapter"],
            }
        )
