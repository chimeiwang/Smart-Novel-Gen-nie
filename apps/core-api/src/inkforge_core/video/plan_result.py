"""视频规划任务在 resultJson 中保存的版本化终态信封。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import JsonValue

_TERMINAL_RESULT_KIND = "video_plan_terminal_result"
_TERMINAL_RESULT_VERSION = "1.0"

VideoPlanTerminalStatus = Literal["completed", "failed"]


class VideoPlanTerminalResultFormatError(ValueError):
    """终态信封或待保留的旧结果不是可安全读取的 JSON。"""


@dataclass(frozen=True, slots=True)
class VideoPlanTerminalResult:
    """从终态信封读取出的原进度和 Agent 原始业务结果。"""

    status: VideoPlanTerminalStatus
    event_id: str
    result: dict[str, JsonValue]
    progress: JsonValue


def encode_video_plan_terminal_result(
    *,
    progress_json: str | None,
    status: VideoPlanTerminalStatus,
    event_id: str,
    result: dict[str, JsonValue],
) -> str:
    """保留原进度并编码一份字段闭合的终态信封。"""

    if not event_id:
        raise VideoPlanTerminalResultFormatError("视频规划终态事件标识不能为空")
    progress: JsonValue = None
    if progress_json is not None:
        try:
            progress = cast(JsonValue, json.loads(progress_json))
        except (TypeError, json.JSONDecodeError) as exc:
            raise VideoPlanTerminalResultFormatError(
                "视频规划原进度不是合法 JSON"
            ) from exc
        if decode_video_plan_terminal_result(progress_json) is not None:
            raise VideoPlanTerminalResultFormatError("不能在既有终态信封外再次包装终态")
    return _canonical_json(
        {
            "kind": _TERMINAL_RESULT_KIND,
            "schemaVersion": _TERMINAL_RESULT_VERSION,
            "progress": progress,
            "outcome": {
                "status": status,
                "eventId": event_id,
                "result": result,
            },
        }
    )


def decode_video_plan_terminal_result(
    result_json: str | None,
) -> VideoPlanTerminalResult | None:
    """读取当前终态信封；其他合法 JSON 作为历史格式返回 None。"""

    if result_json is None:
        return None
    try:
        value = json.loads(result_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise VideoPlanTerminalResultFormatError("视频规划任务结果不是合法 JSON") from exc
    if not isinstance(value, dict) or value.get("kind") != _TERMINAL_RESULT_KIND:
        return None
    if set(value) != {"kind", "schemaVersion", "progress", "outcome"}:
        raise VideoPlanTerminalResultFormatError("视频规划终态信封顶层字段不完整")
    if value["schemaVersion"] != _TERMINAL_RESULT_VERSION:
        raise VideoPlanTerminalResultFormatError("视频规划终态信封版本不受支持")
    outcome = value["outcome"]
    if not isinstance(outcome, dict) or set(outcome) != {"status", "eventId", "result"}:
        raise VideoPlanTerminalResultFormatError("视频规划终态结果字段不完整")
    status = outcome["status"]
    event_id = outcome["eventId"]
    result = outcome["result"]
    if status not in {"completed", "failed"}:
        raise VideoPlanTerminalResultFormatError("视频规划终态类型无效")
    if not isinstance(event_id, str) or not event_id:
        raise VideoPlanTerminalResultFormatError("视频规划终态事件标识无效")
    if not isinstance(result, dict) or not all(isinstance(key, str) for key in result):
        raise VideoPlanTerminalResultFormatError("视频规划终态业务结果必须是对象")
    return VideoPlanTerminalResult(
        status=cast(VideoPlanTerminalStatus, status),
        event_id=event_id,
        result=cast(dict[str, JsonValue], result),
        progress=cast(JsonValue, value["progress"]),
    )


def video_plan_terminal_progress_json(result: VideoPlanTerminalResult) -> str | None:
    """把信封中的原进度恢复成现有检查点读取器可消费的 JSON。"""

    if result.progress is None:
        return None
    return _canonical_json(result.progress)


def video_plan_results_equal(
    left: dict[str, JsonValue],
    right: dict[str, JsonValue],
) -> bool:
    """按规范 JSON 比较结果，避免键顺序影响幂等判断。"""

    return _canonical_json(left) == _canonical_json(right)


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
