from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.writing.idempotency import (
    acquire_idempotency_lock,
    canonical_json_bytes,
    command_idempotency_key,
    enveloped_command_idempotency_key,
    normalize_json_value,
    parse_command_envelope,
    request_fingerprint,
    resolve_idempotency,
)


class RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class RecordingSession:
    def __init__(self, results: list[RowsResult] | None = None) -> None:
        self.results = list(results or [])
        self.calls: list[tuple[object, dict[str, object] | None]] = []

    async def execute(
        self, statement: object, params: dict[str, object] | None = None
    ) -> RowsResult:
        self.calls.append((statement, params))
        if self.results:
            return self.results.pop(0)
        return RowsResult([])


def command_envelope(
    client_request_id: str,
    fingerprint: str,
    *,
    command_kind: str = "start",
) -> str:
    return json.dumps(
        {
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": client_request_id,
                "commandKind": command_kind,
                "resourceIdentity": {
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                },
                "normalizedBody": {"userInstruction": "写出雨夜冲突"},
                "requestFingerprint": fingerprint,
            },
            "job": {"workflow": "long_serial"},
        },
        ensure_ascii=False,
    )


def test_canonical_json_recursively_sorts_keys_and_preserves_unicode() -> None:
    value = {
        "z": "中文",
        "a": {
            "when": datetime(
                2026,
                8,
                5,
                10,
                0,
                0,
                123456,
                tzinfo=timezone(timedelta(hours=8)),
            ),
            "items": (2, 1),
        },
    }

    assert canonical_json_bytes(value) == (
        '{"a":{"items":[2,1],"when":"2026-08-05T02:00:00.123456Z"},'
        '"z":"中文"}'
    ).encode()


@pytest.mark.parametrize(
    ("value", "error_type"),
    [
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (datetime(2026, 8, 5), ValueError),
        ({1: "非字符串 key"}, TypeError),
        (object(), TypeError),
    ],
)
def test_normalize_json_rejects_unstable_values(
    value: object, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        normalize_json_value(value)


def test_request_fingerprint_binds_command_kind_and_resource_identity() -> None:
    fingerprint = request_fingerprint(
        command_kind="start",
        resource_identity={"novelId": "小说-1", "chapterId": "chapter-1"},
        body={"userInstruction": "继续"},
    )

    assert fingerprint == "9f2dee4dfac4f02dbf6d591222a69d1edbd80a7ead7bd43e3872337c86a7c753"
    assert fingerprint != request_fingerprint(
        command_kind="resume",
        resource_identity={"novelId": "小说-1", "chapterId": "chapter-1"},
        body={"userInstruction": "继续"},
    )
    assert fingerprint != request_fingerprint(
        command_kind="start",
        resource_identity={"novelId": "小说-1", "chapterId": "chapter-2"},
        body={"userInstruction": "继续"},
    )


@pytest.mark.asyncio
async def test_idempotency_lock_uses_fixed_sha256_int64_vector() -> None:
    session = RecordingSession()

    await acquire_idempotency_lock(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        client_request_id="client-request-0001",
    )

    statement, params = session.calls[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {"lock_key": 954132569200374116}
    assert hashlib.sha256(b"user-1\0client-request-0001").hexdigest() == (
        "0d3dc28437d1b16474387be307d756bc91a6919db1e257bc84b33699cd1c5639"
    )


def test_command_envelope_parser_is_strict_and_ignores_legacy_payload() -> None:
    fingerprint = "a" * 64
    parsed = parse_command_envelope(command_envelope("request-00000001", fingerprint))

    assert parsed is not None
    assert parsed.clientRequestId == "request-00000001"
    assert parsed.requestFingerprint == fingerprint
    assert parse_command_envelope('{"clientRequestId":"request-00000001"}') is None

    malformed = json.loads(command_envelope("request-00000001", fingerprint))
    malformed["_inkforgeCommand"]["unknown"] = True
    with pytest.raises(ValueError, match="_inkforgeCommand"):
        parse_command_envelope(malformed)


@pytest.mark.asyncio
async def test_resolver_replays_same_writing_command_fingerprint() -> None:
    fingerprint = "b" * 64
    session = RecordingSession(
        [
            RowsResult(
                [
                    (
                        "command-1",
                        command_envelope("request-00000001", fingerprint),
                    )
                ]
            ),
            RowsResult([]),
        ]
    )

    resolved = await resolve_idempotency(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        client_request_id="request-00000001",
        request_fingerprint=fingerprint,
    )

    assert resolved is not None
    assert resolved.record_kind == "writing_command"
    assert resolved.record_id == "command-1"
    assert command_idempotency_key("user-1", "request-00000001") == (
        "user-1:request-00000001"
    )
    assert enveloped_command_idempotency_key(
        "user-1", "request-00000001"
    ) == "v1:user-1:request-00000001"
    assert enveloped_command_idempotency_key(
        "user-1", "request-00000001"
    ) != command_idempotency_key("user-1", "request-00000001")


@pytest.mark.asyncio
async def test_resolver_reads_current_user_workflow_envelopes_linearly() -> None:
    fingerprint = "c" * 64
    session = RecordingSession(
        [
            RowsResult([]),
            RowsResult(
                [
                    ("legacy-run", '{"clientRequestId":"request-00000001"}'),
                    (
                        "workflow-run-1",
                        command_envelope(
                            "request-00000001",
                            fingerprint,
                            command_kind="quality_run",
                        ),
                    ),
                ]
            ),
        ]
    )

    resolved = await resolve_idempotency(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        client_request_id="request-00000001",
        request_fingerprint=fingerprint,
    )

    assert resolved is not None
    assert resolved.record_kind == "workflow_run"
    assert resolved.record_id == "workflow-run-1"
    assert "WorkflowRun" in str(session.calls[1][0])
    assert "userId" in str(session.calls[1][0])


@pytest.mark.asyncio
async def test_resolver_rejects_reused_or_cross_table_client_request_id() -> None:
    requested_fingerprint = "d" * 64
    conflicting_fingerprint = "e" * 64
    session = RecordingSession(
        [
            RowsResult(
                [
                    (
                        "command-1",
                        command_envelope(
                            "request-00000001", conflicting_fingerprint
                        ),
                    )
                ]
            ),
            RowsResult(
                [
                    (
                        "workflow-run-1",
                        command_envelope(
                            "request-00000001",
                            requested_fingerprint,
                            command_kind="quality_run",
                        ),
                    )
                ]
            ),
        ]
    )

    with pytest.raises(ApiError) as error:
        await resolve_idempotency(  # type: ignore[arg-type]
            session,
            user_id="user-1",
            client_request_id="request-00000001",
            request_fingerprint=requested_fingerprint,
        )

    assert error.value.status_code == 409
    assert error.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_historical_bare_writing_payload_never_hits_new_resolver() -> None:
    session = RecordingSession(
        [
            RowsResult(
                [
                    (
                        "legacy-command",
                        json.dumps(
                            {
                                "clientRequestId": "request-00000001",
                                "requestFingerprint": "f" * 64,
                            }
                        ),
                    )
                ]
            ),
            RowsResult([]),
        ]
    )

    resolved = await resolve_idempotency(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        client_request_id="request-00000001",
        request_fingerprint="f" * 64,
    )

    assert resolved is None
