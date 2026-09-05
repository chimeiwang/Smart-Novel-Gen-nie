from __future__ import annotations

import pytest
from inkforge_contracts.agent_updates import (
    AgentUpdatesEvidenceRequestOutput,
    materialize_agent_updates_evidence_request,
)
from inkforge_contracts.execution import canonical_execution_sha256
from pydantic import ValidationError


def test_evidence_request_has_no_model_controlled_identity_and_is_stable() -> None:
    output = {
        "evidenceRequest": [
            {
                "resourceType": "character",
                "resourceId": "character-1",
                "purposeCode": "delete_impact",
            }
        ]
    }
    arguments = dict(
        step_id="step-1",
        request_hash="a" * 64,
        bundle_id="bundle-1",
        bundle_version=2,
        max_input_tokens=80000,
    )
    first = materialize_agent_updates_evidence_request(output, **arguments)
    assert first == materialize_agent_updates_evidence_request(output, **arguments)
    assert first.sourceBundleId == "bundle-1"
    assert first.sourceBundleVersion == 2
    assert first.maxAdditionalBytes == 320000
    assert first.reasonCode == "agent_updates_sources_required"
    assert (
        first.requestId
        == "evidence-"
        + canonical_execution_sha256(
            {"stepId": "step-1", "requestHash": "a" * 64, "items": output["evidenceRequest"]}
        )[:32]
    )
    assert first.items[0].range is None
    changed = arguments | {"step_id": "step-2"}
    assert (
        materialize_agent_updates_evidence_request(output, **changed).requestId != first.requestId
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"evidenceRequest": []},
        {
            "evidenceRequest": [
                {"resourceType": "sql", "resourceId": "data", "purposeCode": "target"}
            ]
        },
        {
            "evidenceRequest": [
                {
                    "resourceType": "character",
                    "resourceId": "character-1",
                    "purposeCode": "target",
                    "range": None,
                }
            ]
        },
        {
            "evidenceRequest": [
                {
                    "resourceType": "character",
                    "resourceId": "character-1",
                    "purposeCode": "replace_tree",
                }
            ]
        },
        {
            "evidenceRequest": [
                {"resourceType": "outline_tree", "resourceId": "novel-1", "purposeCode": "target"}
            ]
        },
        {
            "evidenceRequest": [
                {
                    "resourceType": "reference",
                    "resourceId": "reference-1",
                    "purposeCode": "delete_impact",
                }
            ]
        },
        {
            "evidenceRequest": [
                {"resourceType": "character", "resourceId": "character-1", "purposeCode": "target"}
            ]
            * 2
        },
        {
            "evidenceRequest": [
                {"resourceType": "character", "resourceId": "character-1", "purposeCode": "target"}
            ],
            "summary": "半份候选",
        },
        {
            "evidenceRequest": [
                {"resourceType": "character", "resourceId": "character-1", "purposeCode": "target"}
            ],
            "maxAdditionalBytes": 1000000,
        },
    ],
)
def test_evidence_request_rejects_invalid_scope_or_mixed_candidate(value: object) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesEvidenceRequestOutput.model_validate(value)


def test_evidence_requests_preserve_order_and_accept_explicit_tree() -> None:
    items = [
        {"resourceType": "outline_tree", "resourceId": "novel-1", "purposeCode": "replace_tree"},
        {"resourceType": "world_setting", "resourceId": "novel-1", "purposeCode": "target"},
    ]
    assert AgentUpdatesEvidenceRequestOutput.model_validate({"evidenceRequest": items}).model_dump(
        mode="json"
    ) == {"evidenceRequest": items}
