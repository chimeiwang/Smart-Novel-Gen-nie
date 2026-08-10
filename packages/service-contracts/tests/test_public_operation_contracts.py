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
            "allowedScopeKinds": ("chapter",),
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
