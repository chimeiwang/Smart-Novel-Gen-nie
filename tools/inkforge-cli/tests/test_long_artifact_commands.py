from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from inkforge_cli.api import CoreApiError
from inkforge_cli.commands.long import artifacts
from inkforge_cli.json_types import JsonObject
from inkforge_cli.runtime import CliInputError, CliRuntime


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
    assert body["editedContent"] == content
    assert "editedContentFile" not in body
    assert "profile" not in body


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
