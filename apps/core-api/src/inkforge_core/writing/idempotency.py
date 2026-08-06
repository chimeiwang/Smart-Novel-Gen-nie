from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)
from pydantic import (
    JsonValue as PydanticJsonValue,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Novel, WorkflowRun, WritingRunCommand, WritingTask
from ..errors import ApiError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

RequestFingerprint = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


class InkForgeCommandMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schemaVersion: Literal[1]
    clientRequestId: str = Field(min_length=1, max_length=128)
    commandKind: str = Field(min_length=1)
    resourceIdentity: dict[str, PydanticJsonValue]
    normalizedBody: dict[str, PydanticJsonValue]
    requestFingerprint: RequestFingerprint


@dataclass(frozen=True, slots=True)
class IdempotencyResolution:
    record_kind: Literal["writing_command", "workflow_run"]
    record_id: str
    metadata: InkForgeCommandMetadata


def normalize_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("指纹 JSON 不允许 NaN 或 Infinity")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("指纹 datetime 必须包含时区")
        return value.astimezone(UTC).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("指纹 JSON 对象 key 必须是字符串")
            normalized[key] = normalize_json_value(item)
        return normalized
    raise TypeError(f"指纹 JSON 不支持类型：{type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        normalize_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def request_fingerprint(
    *,
    command_kind: str,
    resource_identity: dict[str, JsonValue],
    body: dict[str, JsonValue],
) -> str:
    value = {
        "commandKind": command_kind,
        "resourceIdentity": resource_identity,
        "body": body,
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def command_idempotency_key(user_id: str, client_request_id: str) -> str:
    return f"{user_id}:{client_request_id}"


def enveloped_command_idempotency_key(
    user_id: str, client_request_id: str
) -> str:
    return f"v1:{user_id}:{client_request_id}"


async def acquire_idempotency_lock(
    session: AsyncSession,
    *,
    user_id: str,
    client_request_id: str,
) -> None:
    digest = hashlib.sha256(f"{user_id}\0{client_request_id}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def parse_command_envelope(
    value: str | dict[str, object] | object,
) -> InkForgeCommandMetadata | None:
    parsed = _json_object(value)
    if parsed is None or "_inkforgeCommand" not in parsed:
        return None
    try:
        metadata = InkForgeCommandMetadata.model_validate(parsed["_inkforgeCommand"])
        normalize_json_value(metadata.resourceIdentity)
        normalize_json_value(metadata.normalizedBody)
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValueError("持久化 _inkforgeCommand envelope 无效") from exc
    return metadata


def logical_command_kind(persisted_kind: str, payload: str | object) -> str:
    parsed = _json_object(payload)
    metadata = parsed.get("_inkforgeCommand") if parsed is not None else None
    logical_kind = metadata.get("commandKind") if isinstance(metadata, dict) else None
    return logical_kind if isinstance(logical_kind, str) and logical_kind else persisted_kind


async def resolve_idempotency(
    session: AsyncSession,
    *,
    user_id: str,
    client_request_id: str,
    request_fingerprint: str | None,
) -> IdempotencyResolution | None:
    writing_rows = (
        await session.execute(
            select(WritingRunCommand.id, WritingRunCommand.payloadJson)
            .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
            .join(Novel, Novel.id == WritingTask.novelId)
            .where(
                WritingRunCommand.idempotencyKey.in_(
                    (
                        enveloped_command_idempotency_key(
                            user_id, client_request_id
                        ),
                        command_idempotency_key(user_id, client_request_id),
                    )
                ),
                Novel.userId == user_id,
            )
        )
    ).all()
    workflow_rows = (
        await session.execute(
            select(WorkflowRun.id, WorkflowRun.input).where(
                WorkflowRun.userId == user_id,
                WorkflowRun.input.is_not(None),
            )
        )
    ).all()

    matches: list[IdempotencyResolution] = []
    for record_kind, rows in (
        ("writing_command", writing_rows),
        ("workflow_run", workflow_rows),
    ):
        for record_id, payload in rows:
            try:
                metadata = parse_command_envelope(payload)
            except ValueError:
                if record_kind == "writing_command" or (
                    _declared_client_request_id(payload) == client_request_id
                ):
                    raise _idempotency_reused(client_request_id) from None
                continue
            if metadata is None or metadata.clientRequestId != client_request_id:
                continue
            matches.append(
                IdempotencyResolution(
                    record_kind=cast(
                        Literal["writing_command", "workflow_run"], record_kind
                    ),
                    record_id=cast(str, record_id),
                    metadata=metadata,
                )
            )

    if not matches:
        return None
    if len(matches) != 1:
        raise _idempotency_reused(client_request_id)
    match = matches[0]
    if (
        request_fingerprint is not None
        and match.metadata.requestFingerprint != request_fingerprint
    ):
        raise _idempotency_reused(client_request_id)
    return match


def _json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(value, dict):
        return None
    if any(not isinstance(key, str) for key in value):
        return None
    return cast(dict[str, object], value)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 不允许常量：{value}")


def _declared_client_request_id(value: object) -> str | None:
    parsed = _json_object(value)
    if parsed is None:
        return None
    metadata = parsed.get("_inkforgeCommand")
    if not isinstance(metadata, dict):
        return None
    client_request_id = metadata.get("clientRequestId")
    return client_request_id if isinstance(client_request_id, str) else None


def _idempotency_reused(client_request_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        message="同一幂等标识已绑定其他请求",
        details={"clientRequestId": client_request_id},
    )
