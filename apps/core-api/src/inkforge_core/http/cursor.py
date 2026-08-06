from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any


class InvalidCursorError(ValueError):
    """游标不是约定的严格 base64url JSON。"""


def encode_run_cursor(*, created_at: datetime, task_id: str) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    payload = json.dumps(
        {"createdAt": created_at.isoformat(), "id": task_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_run_cursor(value: str) -> tuple[datetime, str]:
    if not value or "=" in value:
        raise InvalidCursorError("任务游标格式无效")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
        payload: Any = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("任务游标格式无效") from exc
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise InvalidCursorError("任务游标格式无效")
    if not isinstance(payload, dict) or set(payload) != {"createdAt", "id"}:
        raise InvalidCursorError("任务游标字段无效")
    created_at = payload["createdAt"]
    task_id = payload["id"]
    if not isinstance(created_at, str) or not isinstance(task_id, str) or not task_id:
        raise InvalidCursorError("任务游标字段无效")
    try:
        parsed_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCursorError("任务游标时间无效") from exc
    if parsed_at.tzinfo is None:
        raise InvalidCursorError("任务游标时间必须包含时区")
    return parsed_at, task_id
