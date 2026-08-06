from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from .errors import ApiError


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_expected_updated_at(
    current: datetime | None,
    expected: datetime | None,
    *,
    code: str,
) -> None:
    current_utc = _utc(current)
    if current_utc == _utc(expected):
        return
    raise ApiError(
        status_code=409,
        code=code,
        message="资源版本已变化，请重新读取",
        details={
            "currentUpdatedAt": current_utc.isoformat() if current_utc is not None else None
        },
    )


def next_utc_timestamp(current: datetime | None) -> datetime:
    now = datetime.now(UTC)
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    current_utc = _utc(current)
    if current_utc is None:
        return now
    candidate = max(now, current_utc + timedelta(microseconds=1))
    remainder = candidate.microsecond % 1000
    if remainder:
        candidate += timedelta(microseconds=1000 - remainder)
    return candidate


def command_resource_id(
    namespace: str,
    user_id: str,
    novel_id: str,
    request_id: str,
) -> str:
    payload = "\x1f".join((namespace, user_id, novel_id, request_id)).encode("utf-8")
    return f"ifc_{hashlib.sha256(payload).hexdigest()}"
