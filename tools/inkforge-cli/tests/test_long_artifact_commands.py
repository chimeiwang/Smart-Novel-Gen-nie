from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from inkforge_cli.api import CoreApiError
from inkforge_cli.commands.long import artifacts
from inkforge_cli.json_types import JsonObject
from inkforge_cli.runtime import CliInputError, CliRuntime, CoreResponseContractError


@dataclass
class RecordingApi:
    responses: list[Any] = field(default_factory=list)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        response = self.responses.pop(0) if self.responses else {}
        if isinstance(response, Exception):
            raise response
        return response


@dataclass
class RuntimeStub:
    api: RecordingApi

    def require_api(self) -> RecordingApi:
        return self.api


def runtime(api: RecordingApi) -> CliRuntime:
    return cast(CliRuntime, RuntimeStub(api))


def payload(**values: object) -> JsonObject:
    return cast(JsonObject, values)


def writing_artifact() -> JsonObject:
    return {
        "id": "draft-1",
        "engineVersion": 2,
        "revision": 7,
        "sourceBindingStatus": "verified",
        "kind": "chapter_draft",
        "payload": {
            "kind": "chapter_draft",
            "operation": "write_chapter",
            "target": {"mode": "existing_chapter", "chapterId": "c1"},
            "content": "初始完整草案",
        },
    }


def agent_updates_artifact() -> JsonObject:
    return {
        "id": "updates-1",
        "engineVersion": 2,
        "revision": 4,
        "sourceBindingStatus": "verified",
        "kind": "agent_updates",
        "payload": {
            "kind": "agent_updates",
            "summary": "更新人物和世界设定",
            "updates": {
                "characters": [{"action": "create", "name": "林舟"}],
                "worldSetting": "雨城仍在封锁中。",
            },
        },
    }


@pytest.mark.parametrize("field_name", ["editedContent", "editedContentFile"])
def test_v2_full_edit_preserves_content_and_reads_exact_revision(
    tmp_path: Path, field_name: str,
) -> None:
    content = "  甲" * 30_000 + "\r\n尾部e\u0301😀\r\n"
    source = tmp_path / "完整正文.txt"
    source.write_bytes(content.encode("utf-8"))
    api = RecordingApi(responses=[writing_artifact(), {"decision": "approve"}])
    artifacts.approve(runtime(api), payload(
        artifactId="draft-1", engineVersion=2, expectedRevision=7,
        clientRequestId="draft-full-approve-0001",
        **{field_name: str(source) if field_name.endswith("File") else content},
    ))
    assert api.calls[0] == (
        "GET", "/api/v1/review-artifacts/draft-1", {"params": {"revision": 7}},
    )
    assert api.calls[-1][2]["json"]["editedContent"] == content
    assert "editedContentFile" not in api.calls[-1][2]["json"]


@pytest.mark.parametrize(
    "selected_update_refs",
    [
        None,
        [],
        [
            {"section": "characters", "index": 0},
            {"section": "worldSetting"},
        ],
    ],
)
def test_v2_agent_updates_approve_preserves_selected_update_refs(
    selected_update_refs: object,
) -> None:
    api = RecordingApi(
        responses=[agent_updates_artifact(), {"decision": "approve"}],
    )

    artifacts.approve(
        runtime(api),
        payload(
            artifactId="updates-1",
            engineVersion=2,
            expectedRevision=4,
            clientRequestId="updates-approve-0001",
            selectedUpdateRefs=selected_update_refs,
        ),
    )

    assert api.calls[0] == (
        "GET",
        "/api/v1/review-artifacts/updates-1",
        {"params": {"revision": 4}},
    )
    body = api.calls[-1][2]["json"]
    assert "selectedUpdateRefs" in body
    assert body["selectedUpdateRefs"] == selected_update_refs


@pytest.mark.parametrize(
    "changed",
    [
        {"kind": "beat_plan"},
        {"payload": {"kind": "beat_plan", "updates": {}}},
        {"payload": {"kind": "agent_updates"}},
        {"payload": {"kind": "agent_updates", "updates": []}},
    ],
)
def test_v2_selected_update_refs_require_exact_agent_updates_artifact(
    changed: dict[str, object],
) -> None:
    artifact = agent_updates_artifact()
    artifact.update(cast(JsonObject, changed))
    api = RecordingApi(responses=[artifact])

    with pytest.raises(CliInputError) as caught:
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="updates-1",
                engineVersion=2,
                expectedRevision=4,
                clientRequestId="updates-invalid-0001",
                selectedUpdateRefs=[],
            ),
        )

    assert caught.value.code == "V2_EDIT_FIELDS_FORBIDDEN"
    assert [call[0] for call in api.calls] == ["GET"]


@pytest.mark.parametrize(
    "edited",
    [
        {"editedContent": "不允许结构化全文编辑"},
        {"editedReplacement": "不允许结构化选区编辑"},
    ],
)
def test_v2_agent_updates_approve_rejects_text_edit_fields(
    edited: dict[str, object],
) -> None:
    api = RecordingApi(responses=[agent_updates_artifact()])

    with pytest.raises(CliInputError) as caught:
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="updates-1",
                engineVersion=2,
                expectedRevision=4,
                clientRequestId="updates-no-text-0001",
                **edited,
            ),
        )

    assert caught.value.code == "V2_EDIT_FIELDS_FORBIDDEN"
    assert [call[0] for call in api.calls] == ["GET"]


def test_v2_agent_updates_revise_still_rejects_selected_update_refs() -> None:
    api = RecordingApi(responses=[agent_updates_artifact()])

    with pytest.raises(CliInputError) as caught:
        artifacts.revise(
            runtime(api),
            payload(
                artifactId="updates-1",
                engineVersion=2,
                expectedRevision=4,
                clientRequestId="updates-revise-0001",
                selectedUpdateRefs=[],
                userMessage="请重新整理",
            ),
        )

    assert caught.value.code == "V2_EDIT_FIELDS_FORBIDDEN"
    assert [call[0] for call in api.calls] == ["GET"]


def test_v2_approve_and_revise_keep_prior_null_omission_outside_partial_apply() -> None:
    approve_api = RecordingApi(
        responses=[writing_artifact(), {"decision": "approve"}],
    )
    artifacts.approve(
        runtime(approve_api),
        payload(
            artifactId="draft-1",
            engineVersion=2,
            expectedRevision=7,
            clientRequestId="draft-null-selection-0001",
            selectedUpdateRefs=None,
        ),
    )
    assert "selectedUpdateRefs" not in approve_api.calls[-1][2]["json"]

    revise_api = RecordingApi(
        responses=[agent_updates_artifact(), {"decision": "revise"}],
    )
    artifacts.revise(
        runtime(revise_api),
        payload(
            artifactId="updates-1",
            engineVersion=2,
            expectedRevision=4,
            clientRequestId="updates-revise-null-0001",
            selectedUpdateRefs=None,
            userMessage="请重新整理",
        ),
    )
    assert "selectedUpdateRefs" not in revise_api.calls[-1][2]["json"]


@pytest.mark.parametrize("extra", [
    {"editedContent": " \n\t"},
    {"editedReplacement": "选区"},
    {"selectedUpdateRefs": []},
])
def test_v2_full_edit_rejects_blank_or_other_artifact_fields(extra: dict[str, object]) -> None:
    api = RecordingApi(responses=[writing_artifact()])
    with pytest.raises(CliInputError):
        artifacts.approve(runtime(api), payload(
            artifactId="draft-1", engineVersion=2, expectedRevision=7,
            clientRequestId="draft-invalid-0001", **extra,
        ))
    assert [call[0] for call in api.calls] == ["GET"]


@pytest.mark.parametrize("field_name", ["editedContent", "editedReplacement"])
def test_v2_plan_rejects_both_edit_types(field_name: str) -> None:
    artifact = writing_artifact()
    artifact.update(kind="beat_plan", payload={"operation": "plan_chapter"})
    api = RecordingApi(responses=[artifact])
    with pytest.raises(CliInputError) as caught:
        artifacts.approve(runtime(api), payload(
            artifactId="draft-1", engineVersion=2, expectedRevision=7,
            clientRequestId="plan-no-edit-0001", **{field_name: "编辑内容"},
        ))
    assert caught.value.code == "V2_EDIT_FIELDS_FORBIDDEN"
    assert [call[0] for call in api.calls] == ["GET"]


@pytest.mark.parametrize("changed", [{"id": "other"}, {"revision": 8}, {"revision": True}])
def test_v2_decision_rejects_wrong_exact_artifact(changed: dict[str, object]) -> None:
    artifact = writing_artifact()
    artifact.update(cast(JsonObject, changed))
    api = RecordingApi(responses=[artifact])
    with pytest.raises(CoreResponseContractError):
        artifacts.approve(runtime(api), payload(
            artifactId="draft-1", engineVersion=2, expectedRevision=7,
            clientRequestId="draft-identity-0001", editedContent="完整正文",
        ))
    assert [call[0] for call in api.calls] == ["GET"]


@pytest.mark.parametrize(
    ("handler", "decision", "extra"),
    [
        (artifacts.approve, "approve", {"selectedUpdateRefs": [{"section": "正文"}]}),
        (artifacts.revise, "revise", {"userMessage": "请加强冲突"}),
    ],
)
def test_approve_and_revise_preflight_verified_source_then_post_fixed_body(
    handler: Any,
    decision: str,
    extra: dict[str, object],
) -> None:
    api = RecordingApi(
        responses=[
            {"id": "artifact /?#", "sourceBindingStatus": "verified"},
            {"artifactId": "artifact /?#", "decision": decision},
        ]
    )

    result = handler(
        runtime(api),
        payload(
            artifactId="artifact /?#",
            clientRequestId="decision-request-0001",
            expectedRevision=3,
            profile="production",
            **extra,
        ),
    )

    encoded = "artifact%20%2F%3F%23"
    assert result["decision"] == decision
    assert api.calls == [
        ("GET", f"/api/v1/review-artifacts/{encoded}", {}),
        (
            "POST",
            f"/api/v1/review-artifacts/{encoded}/decision",
            {
                "json": {
                    "engineVersion": 1,
                    "clientRequestId": "decision-request-0001",
                    "expectedRevision": 3,
                    "decision": decision,
                    **extra,
                }
            },
        ),
    ]


def test_edited_content_file_is_read_as_exact_utf8_without_newline_changes(
    tmp_path: Path,
) -> None:
    content = "甲" * 80_000 + "\r\n尾部e\u0301😀\r\n"
    source = tmp_path / "edited.txt"
    source.write_bytes(content.encode("utf-8"))
    api = RecordingApi(
        responses=[
            {"sourceBindingStatus": "verified"},
            {"artifactId": "artifact-1", "decision": "approve"},
        ]
    )

    artifacts.approve(
        runtime(api),
        payload(
            artifactId="artifact-1",
            clientRequestId="decision-request-0001",
            expectedRevision=1,
            editedContentFile=str(source),
            profile="default",
        ),
    )

    body = api.calls[1][2]["json"]
    assert body["engineVersion"] == 1
    assert body["editedContent"] == content
    assert "editedContentFile" not in body
    assert "profile" not in body


def test_selection_artifact_uses_structured_edited_replacement_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "replacement.txt"
    replacement = "鏂版枃\r\n尾部"
    source.write_bytes(replacement.encode("utf-8"))
    api = RecordingApi(
        responses=[
            {
                "sourceBindingStatus": "verified",
                "kind": "chapter_draft",
                "payload": {"target": {"mode": "replace_selection"}},
                "diff": {"before": "旧文", "after": replacement},
            },
            {"artifactId": "artifact-1", "decision": "approve"},
        ]
    )

    artifacts.approve(
        runtime(api),
        payload(
            artifactId="artifact-1",
            clientRequestId="decision-request-0001",
            expectedRevision=1,
            editedReplacementFile=str(source),
        ),
    )

    body = api.calls[1][2]["json"]
    assert body["engineVersion"] == 1
    assert body["editedReplacement"] == replacement
    assert "editedReplacementFile" not in body
    assert "editedContent" not in body


def test_selection_artifact_rejects_full_edited_content() -> None:
    api = RecordingApi(
        responses=[
            {
                "sourceBindingStatus": "verified",
                "kind": "chapter_draft",
                "payload": {"target": {"mode": "replace_selection"}},
                "diff": {"before": "旧文", "after": "新文"},
            }
        ]
    )

    with pytest.raises(CliInputError):
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=1,
                editedContent="全文",
            ),
        )

    assert [call[0] for call in api.calls] == ["GET"]


def test_full_artifact_rejects_structured_edited_replacement() -> None:
    api = RecordingApi(
        responses=[
            {
                "sourceBindingStatus": "verified",
                "kind": "chapter_draft",
                "payload": {"target": {"mode": "existing_chapter"}},
                "diff": {"before": "旧文", "after": "新文"},
            }
        ]
    )

    with pytest.raises(CliInputError):
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=1,
                editedReplacement="选区替换",
            ),
        )

    assert [call[0] for call in api.calls] == ["GET"]


@pytest.mark.parametrize("expected_revision", [None, 0, -1, True, "1"])
def test_decision_requires_a_positive_integer_expected_revision(
    expected_revision: object,
) -> None:
    api = RecordingApi()
    values: dict[str, object] = {
        "artifactId": "artifact-1",
        "clientRequestId": "decision-request-0001",
    }
    if expected_revision is not None:
        values["expectedRevision"] = expected_revision

    with pytest.raises(CliInputError) as caught:
        artifacts.approve(runtime(api), payload(**values))

    assert caught.value.code == "INVALID_EXPECTED_REVISION"
    assert api.calls == []


@pytest.mark.parametrize(
    ("handler", "decision", "extra"),
    [
        (artifacts.approve, "approve", {}),
        (artifacts.revise, "revise", {"userMessage": "请重新生成"}),
        (artifacts.discard, "discard", {}),
    ],
)
@pytest.mark.parametrize("engine_version", [1, 2])
def test_all_decisions_send_explicit_valid_engine_version(
    handler: Any,
    decision: str,
    extra: dict[str, object],
    engine_version: int,
) -> None:
    responses: list[Any] = []
    if decision != "discard":
        responses.append({
            "id": "artifact-1", "revision": 1,
            "engineVersion": engine_version, "sourceBindingStatus": "verified",
        })
    responses.append({"artifactId": "artifact-1", "decision": decision})
    api = RecordingApi(responses=responses)

    handler(
        runtime(api),
        payload(
            artifactId="artifact-1",
            clientRequestId="decision-engine-0001",
            expectedRevision=1,
            engineVersion=engine_version,
            **extra,
        ),
    )

    assert api.calls[-1][2]["json"]["engineVersion"] == engine_version


@pytest.mark.parametrize(
    "handler",
    [artifacts.approve, artifacts.revise, artifacts.discard],
)
@pytest.mark.parametrize("engine_version", [None, 0, 3, True, 1.5, "2"])
def test_all_decisions_reject_invalid_engine_version_before_network(
    handler: Any,
    engine_version: object,
) -> None:
    api = RecordingApi()
    values: dict[str, object] = {
        "artifactId": "artifact-1",
        "clientRequestId": "decision-engine-0001",
        "expectedRevision": 1,
        "engineVersion": engine_version,
    }
    if handler is artifacts.revise:
        values["userMessage"] = "请重新生成"

    with pytest.raises(CliInputError) as caught:
        handler(runtime(api), payload(**values))

    assert caught.value.code == "INVALID_ENGINE_VERSION"
    assert api.calls == []


def test_approve_rejects_edited_content_and_file_together_before_preflight(
    tmp_path: Path,
) -> None:
    source = tmp_path / "edited.txt"
    source.write_text("文件正文", encoding="utf-8")
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=1,
                editedContent="内联正文",
                editedContentFile=str(source),
            ),
        )

    assert caught.value.code == "EDITED_CONTENT_CONFLICT"
    assert api.calls == []


@pytest.mark.parametrize("user_message", [None, "", "   "])
def test_revise_requires_a_non_empty_user_message(user_message: object) -> None:
    api = RecordingApi()
    values: dict[str, object] = {
        "artifactId": "artifact-1",
        "clientRequestId": "decision-request-0001",
        "expectedRevision": 1,
    }
    if user_message is not None:
        values["userMessage"] = user_message

    with pytest.raises(CliInputError) as caught:
        artifacts.revise(runtime(api), payload(**values))

    assert caught.value.code == "USER_MESSAGE_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize(
    "forbidden",
    [
        {"editedContent": "正文"},
        {"editedContentFile": "edited.txt"},
        {"selectedUpdateRefs": [{"section": "正文"}]},
        {"selectedUpdateRefs": None},
    ],
)
def test_discard_rejects_editing_fields_without_fetching_artifact(
    forbidden: dict[str, object],
) -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        artifacts.discard(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=2,
                **forbidden,
            ),
        )

    assert caught.value.code == "DISCARD_EDIT_FIELDS_FORBIDDEN"
    assert api.calls == []


@pytest.mark.parametrize("status", ["legacy_missing", "not_yet_supported"])
def test_approve_and_revise_reject_unverified_source_binding_locally(
    status: str,
) -> None:
    api = RecordingApi(responses=[{"sourceBindingStatus": status}])

    with pytest.raises(CoreApiError) as caught:
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=1,
            ),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "SOURCE_BINDING_NOT_VERIFIED"
    assert caught.value.details == {
        "artifactId": "artifact-1",
        "sourceBindingStatus": status,
    }
    assert [call[0] for call in api.calls] == ["GET"]


def test_discard_skips_source_preflight_and_still_sends_expected_revision() -> None:
    api = RecordingApi(responses=[{"artifactId": "artifact-1", "decision": "discard"}])

    artifacts.discard(
        runtime(api),
        payload(
            artifactId="artifact-1",
            clientRequestId="decision-request-0001",
            expectedRevision=4,
        ),
    )

    assert api.calls == [
        (
            "POST",
            "/api/v1/review-artifacts/artifact-1/decision",
            {
                "json": {
                    "engineVersion": 1,
                    "clientRequestId": "decision-request-0001",
                    "expectedRevision": 4,
                    "decision": "discard",
                }
            },
        )
    ]


def test_source_conflict_from_core_preserves_all_public_error_details() -> None:
    conflict = CoreApiError(
        409,
        code="ARTIFACT_SOURCE_CONFLICT",
        message="草案来源已经变化",
        details={"resourceType": "chapter", "expected": "v1", "current": "v2"},
        request_id="request-server-1",
    )
    api = RecordingApi(
        responses=[{"sourceBindingStatus": "verified"}, conflict]
    )

    with pytest.raises(CoreApiError) as caught:
        artifacts.approve(
            runtime(api),
            payload(
                artifactId="artifact-1",
                clientRequestId="decision-request-0001",
                expectedRevision=1,
            ),
        )

    assert caught.value is conflict
    assert caught.value.details == {
        "resourceType": "chapter",
        "expected": "v1",
        "current": "v2",
    }
    assert caught.value.request_id == "request-server-1"
