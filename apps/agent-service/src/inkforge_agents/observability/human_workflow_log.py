from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from ..runtime.model_runtime import ModelCallLogRecord

_LOG_MAGIC = b"INKFORGE-HUMAN-LOG/2\n"
_FRAME_PREFIX_PATTERN = re.compile(rb"INKFORGE-FRAME ([0-9]+) ([0-9]+)\n")


@dataclass(frozen=True, slots=True)
class WorkflowRunSummary:
    runId: str
    taskId: str
    runKind: str
    userId: str
    novelId: str
    chapterId: str | None
    startedAt: str
    endedAt: str
    status: str


@dataclass(frozen=True, slots=True)
class WorkflowLogDetail:
    summary: WorkflowRunSummary
    content: str


@dataclass(frozen=True, slots=True)
class _LogFrame:
    header: dict[str, Any]
    content: str | None


class HumanWorkflowLog:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._lock = threading.RLock()
        self._paths: dict[str, Path] = {}

    def start_run(
        self,
        *,
        run_id: str,
        task_id: str,
        run_kind: str,
        user_id: str,
        novel_id: str,
        chapter_id: str | None,
    ) -> Path:
        with self._lock:
            path = self._find_path(run_id) or self._new_path(run_id)
            timestamp = _now()
            if not path.exists():
                metadata = {
                    "runId": run_id,
                    "taskId": task_id,
                    "userId": user_id,
                    "novelId": novel_id,
                    "chapterId": chapter_id,
                    "startedAt": timestamp,
                }
                _create_v2_log(
                    path,
                    _LogFrame(
                        header={"type": "metadata", **metadata},
                        content="运行信息：" + _json(metadata) + "\n",
                    ),
                )
            frames = _ensure_v2_log(path)
            run_number = _next_sequence(frames, "run")
            _append_frame(
                path,
                _LogFrame(
                    header={
                        "type": "run",
                        "sequence": run_number,
                        "runKind": run_kind,
                        "startedAt": timestamp,
                    },
                    content=f"\nR{run_number:02d} {run_kind}\n开始时间：{timestamp}\n",
                ),
            )
            self._paths[run_id] = path
            return path

    def record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        with self._lock:
            path = self._require_path(run_id)
            frames = _ensure_v2_log(path)
            sequence = _next_sequence(frames, "state")
            _append_frame(
                path,
                _LogFrame(
                    header={"type": "state", "sequence": sequence},
                    content=(
                        f"\nS{sequence:03d} 状态切换\n"
                        f"节点：{node}\n字段：{_json(changes)}\n"
                    ),
                ),
            )

    def record_model_call(self, record: ModelCallLogRecord) -> None:
        with self._lock:
            path = self._require_path(record.context.runId)
            frames = _ensure_v2_log(path)
            sequence = _next_sequence(frames, "model")
            billing_request_id = record.billingRequestId or "无"
            usage = record.usage
            sections = [
                f"\nA{sequence:02d} 智能体：{record.context.agentId}",
                f"任务标识：{record.context.taskId}",
                f"运行标识：{record.context.runId}",
                f"计费请求标识：{billing_request_id}",
                f"模型：{record.provider}/{record.model}",
                "Token 消耗："
                f"输入 {usage.promptTokens} | "
                f"缓存 {usage.cachedTokens} | "
                f"输出 {usage.completionTokens} | "
                f"合计 {usage.totalTokens}",
                "请求消息：",
            ]
            for message in record.messages:
                role = _role_label(message.get("role"))
                value = message.get("content")
                sections.extend((f"[{role}]", value if isinstance(value, str) else _json(value)))
            sections.extend(
                (
                    "模型响应：",
                    record.output,
                    f"完成原因：{record.finishReason}",
                    "供应商原始原因："
                    + (
                        record.rawFinishReason
                        if record.rawFinishReason is not None
                        else "未提供"
                    ),
                    "",
                )
            )
            _append_frame(
                path,
                _LogFrame(
                    header={"type": "model", "sequence": sequence},
                    content="\n".join(sections),
                ),
            )

    def finish_run(self, run_id: str, status: str) -> Path:
        with self._lock:
            path = self._require_path(run_id)
            _ensure_v2_log(path)
            ended_at = _now()
            _append_frame(
                path,
                _LogFrame(
                    header={"type": "finish", "endedAt": ended_at, "status": status},
                    content=f"结束时间：{ended_at}\n结束状态：{status}\n",
                ),
            )
            return path

    def list_runs(self, user_id: str) -> list[WorkflowRunSummary]:
        with self._lock:
            summaries = [
                summary
                for path in self._root.rglob("*.log")
                if (summary := self._summary(path)) is not None and summary.userId == user_id
            ]
            return sorted(summaries, key=lambda item: item.startedAt, reverse=True)

    def read_run(self, run_id: str, user_id: str) -> WorkflowLogDetail:
        with self._lock:
            path = self._find_path(run_id)
            summary = self._summary(path) if path is not None else None
            if path is None or summary is None or summary.userId != user_id:
                raise LookupError("运行日志不存在或无权访问")
            content = (
                _render_v2_log(path)
                if _is_v2_log(path)
                else _legacy_display(path.read_text(encoding="utf-8"))
            )
            return WorkflowLogDetail(summary=summary, content=content)

    def _new_path(self, run_id: str) -> Path:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        digest = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        return self._root / day / f"{digest}.log"

    def _find_path(self, run_id: str) -> Path | None:
        cached = self._paths.get(run_id)
        if cached is not None and cached.exists():
            return cached
        for path in self._root.rglob("*.log") if self._root.exists() else ():
            summary = self._summary(path)
            if summary is not None and summary.runId == run_id:
                self._paths[run_id] = path
                return path
        return None

    def _require_path(self, run_id: str) -> Path:
        path = self._find_path(run_id)
        if path is None:
            raise LookupError("运行日志不存在")
        return path

    def _summary(self, path: Path | None) -> WorkflowRunSummary | None:
        if path is None or not path.is_file():
            return None
        if _is_v2_log(path):
            return _v2_summary(_read_v2_frames(path, include_content=False))
        return _legacy_summary(path.read_text(encoding="utf-8"))


def _legacy_summary(content: str) -> WorkflowRunSummary | None:
    first_line = content.splitlines()[0] if content else ""
    if not first_line.startswith("运行信息："):
        return None
    try:
        metadata = json.loads(first_line.removeprefix("运行信息："))
        run_id = str(metadata["runId"])
        task_id = str(metadata["taskId"])
        user_id = str(metadata["userId"])
        novel_id = str(metadata["novelId"])
        started_at = str(metadata["startedAt"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    run_kinds = re.findall(r"(?m)^R\d+ (.+)$", content)
    ended = re.findall(r"(?m)^结束时间：(.+)$", content)
    statuses = re.findall(r"(?m)^结束状态：(.+)$", content)
    return WorkflowRunSummary(
        runId=run_id,
        taskId=task_id,
        runKind=run_kinds[-1] if run_kinds else "未知运行",
        userId=user_id,
        novelId=novel_id,
        chapterId=(
            str(metadata["chapterId"])
            if metadata.get("chapterId") is not None
            else None
        ),
        startedAt=started_at,
        endedAt=ended[-1] if ended else started_at,
        status=statuses[-1] if statuses else "执行中",
    )


def _v2_summary(frames: list[_LogFrame]) -> WorkflowRunSummary | None:
    metadata = next(
        (frame.header for frame in frames if frame.header.get("type") == "metadata"),
        None,
    )
    if metadata is None:
        return None
    try:
        run_id = str(metadata["runId"])
        task_id = str(metadata["taskId"])
        user_id = str(metadata["userId"])
        novel_id = str(metadata["novelId"])
        started_at = str(metadata["startedAt"])
    except (KeyError, TypeError):
        return None
    run_headers = [frame.header for frame in frames if frame.header.get("type") == "run"]
    finish_headers = [
        frame.header for frame in frames if frame.header.get("type") == "finish"
    ]
    legacy_header = next(
        (frame.header for frame in frames if frame.header.get("type") == "legacy"),
        {},
    )
    run_kind = (
        str(run_headers[-1].get("runKind", "未知运行"))
        if run_headers
        else str(legacy_header.get("runKind", "未知运行"))
    )
    ended_at = (
        str(finish_headers[-1].get("endedAt", started_at))
        if finish_headers
        else str(legacy_header.get("endedAt", started_at))
    )
    status = (
        str(finish_headers[-1].get("status", "执行中"))
        if finish_headers
        else str(legacy_header.get("status", "执行中"))
    )
    chapter_id = metadata.get("chapterId")
    return WorkflowRunSummary(
        runId=run_id,
        taskId=task_id,
        runKind=run_kind,
        userId=user_id,
        novelId=novel_id,
        chapterId=str(chapter_id) if chapter_id is not None else None,
        startedAt=started_at,
        endedAt=ended_at,
        status=status,
    )


def _ensure_v2_log(path: Path) -> list[_LogFrame]:
    if _is_v2_log(path):
        return _read_v2_frames(path, include_content=False)
    legacy_content = path.read_text(encoding="utf-8")
    summary = _legacy_summary(legacy_content)
    if summary is None:
        raise ValueError("旧版人工日志缺少有效运行信息")
    counts = {
        "run": len(re.findall(r"(?m)^R\d+ .+$", legacy_content)),
        "state": len(re.findall(r"(?m)^S\d+ 状态切换$", legacy_content)),
        "model": len(re.findall(r"(?m)^A\d+ 智能体：", legacy_content)),
    }
    frames = [
        _LogFrame(
            header={
                "type": "metadata",
                "runId": summary.runId,
                "taskId": summary.taskId,
                "userId": summary.userId,
                "novelId": summary.novelId,
                "chapterId": summary.chapterId,
                "startedAt": summary.startedAt,
            },
            content="",
        ),
        _LogFrame(
            header={
                "type": "legacy",
                "counts": counts,
                "runKind": summary.runKind,
                "endedAt": summary.endedAt,
                "status": summary.status,
            },
            content=_legacy_display(legacy_content),
        ),
    ]
    _replace_with_v2_log(path, frames)
    return frames


def _next_sequence(frames: list[_LogFrame], frame_type: str) -> int:
    sequence = sum(1 for frame in frames if frame.header.get("type") == frame_type)
    for frame in frames:
        if frame.header.get("type") != "legacy":
            continue
        counts = frame.header.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("旧版人工日志计数信息无效")
        legacy_count = counts.get(frame_type, 0)
        if type(legacy_count) is not int or legacy_count < 0:
            raise ValueError("旧版人工日志计数信息无效")
        sequence += legacy_count
    return sequence + 1


def _is_v2_log(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(_LOG_MAGIC)) == _LOG_MAGIC


def _read_v2_frames(path: Path, *, include_content: bool) -> list[_LogFrame]:
    frames: list[_LogFrame] = []
    with path.open("rb") as handle:
        if handle.read(len(_LOG_MAGIC)) != _LOG_MAGIC:
            raise ValueError("人工日志版本标识无效")
        while marker := handle.readline():
            match = _FRAME_PREFIX_PATTERN.fullmatch(marker)
            if match is None:
                raise ValueError("人工日志帧头无效")
            header_length = int(match.group(1))
            content_length = int(match.group(2))
            header_bytes = _read_exact(handle, header_length)
            if handle.read(1) != b"\n":
                raise ValueError("人工日志结构头边界无效")
            if include_content:
                content = _read_exact(handle, content_length).decode("utf-8")
            else:
                handle.seek(content_length, 1)
                content = None
            if handle.read(1) != b"\n":
                raise ValueError("人工日志正文边界无效")
            try:
                header = json.loads(header_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("人工日志结构头不是有效 JSON") from exc
            if not isinstance(header, dict) or not isinstance(header.get("type"), str):
                raise ValueError("人工日志结构头字段无效")
            frames.append(_LogFrame(header=header, content=content))
    return frames


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    value = handle.read(length)
    if len(value) != length:
        raise ValueError("人工日志帧不完整")
    return value


def _render_v2_log(path: Path) -> str:
    frames = _read_v2_frames(path, include_content=True)
    return "".join(frame.content or "" for frame in frames)


def _create_v2_log(path: Path, first_frame: _LogFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_LOG_MAGIC + _encode_frame(first_frame))


def _replace_with_v2_log(path: Path, frames: list[_LogFrame]) -> None:
    content = _LOG_MAGIC + b"".join(_encode_frame(frame) for frame in frames)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(content)
    temporary_path.replace(path)


def _append_frame(path: Path, frame: _LogFrame) -> None:
    with path.open("ab") as handle:
        handle.write(_encode_frame(frame))


def _encode_frame(frame: _LogFrame) -> bytes:
    if frame.content is None:
        raise ValueError("写入人工日志时正文不能为空")
    header = _json(frame.header).encode("utf-8")
    content = frame.content.encode("utf-8")
    marker = f"INKFORGE-FRAME {len(header)} {len(content)}\n".encode()
    return marker + header + b"\n" + content + b"\n"


def _legacy_display(content: str) -> str:
    suffix = "" if content.endswith("\n") else "\n"
    return (
        "旧版日志边界（只读兼容，以下原文不参与新版结构解析）：\n"
        + content
        + suffix
        + "旧版日志边界结束\n"
    )


def _role_label(value: object) -> str:
    labels = {
        "system": "系统",
        "user": "用户",
        "assistant": "智能体",
        "tool": "工具",
    }
    return labels.get(str(value), str(value or "未知"))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _now() -> str:
    return datetime.now(UTC).isoformat()
