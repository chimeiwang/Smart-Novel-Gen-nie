from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
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


@dataclass(frozen=True, slots=True)
class _FrameScan:
    frames: list[_LogFrame]
    source: bytes
    last_good_offset: int
    tail: bytes
    error: str | None


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
            frames = _ensure_v2_log(path, expected_run_id=run_id)
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
            frames = _ensure_v2_log(path, expected_run_id=run_id)
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
            frames = _ensure_v2_log(path, expected_run_id=record.context.runId)
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
            _ensure_v2_log(path, expected_run_id=run_id)
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
                else _legacy_display(_read_utf8_exact(path))
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
        try:
            if _is_v2_log(path):
                scan = _scan_v2_frames(path, include_content=False)
                return _v2_summary(scan.frames, tail_damaged=scan.error is not None)
            return _legacy_summary(_read_utf8_exact(path))
        except (OSError, UnicodeError, ValueError):
            return None


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
    return WorkflowRunSummary(
        runId=run_id,
        taskId=task_id,
        runKind="旧版未验证",
        userId=user_id,
        novelId=novel_id,
        chapterId=(
            str(metadata["chapterId"])
            if metadata.get("chapterId") is not None
            else None
        ),
        startedAt=started_at,
        endedAt=started_at,
        status="旧版未验证",
    )


def _v2_summary(
    frames: list[_LogFrame],
    *,
    tail_damaged: bool = False,
) -> WorkflowRunSummary | None:
    metadata_frames = [
        frame.header for frame in frames if frame.header.get("type") == "metadata"
    ]
    if (
        len(metadata_frames) != 1
        or not frames
        or frames[0].header.get("type") != "metadata"
    ):
        return None
    metadata = metadata_frames[0]
    run_id = _required_metadata_text(metadata, "runId")
    task_id = _required_metadata_text(metadata, "taskId")
    user_id = _required_metadata_text(metadata, "userId")
    novel_id = _required_metadata_text(metadata, "novelId")
    started_at = _required_metadata_text(metadata, "startedAt")
    if (
        run_id is None
        or task_id is None
        or user_id is None
        or novel_id is None
        or started_at is None
    ):
        return None
    run_headers = [frame.header for frame in frames if frame.header.get("type") == "run"]
    finish_headers = [
        frame.header for frame in frames if frame.header.get("type") == "finish"
    ]
    legacy_header = next(
        (frame.header for frame in frames if frame.header.get("type") == "legacy"),
        {},
    )
    run_kind = str(run_headers[-1].get("runKind", "未知运行")) if run_headers else (
        "旧版未验证" if legacy_header else "未知运行"
    )
    ended_at = (
        str(finish_headers[-1].get("endedAt", started_at))
        if finish_headers
        else started_at
    )
    trusted_status = (
        str(finish_headers[-1].get("status", "执行中"))
        if finish_headers
        else ("旧版未验证" if legacy_header and not run_headers else "执行中")
    )
    chapter_id = metadata.get("chapterId")
    if chapter_id is not None and (
        not isinstance(chapter_id, str) or not chapter_id.strip()
    ):
        return None
    return WorkflowRunSummary(
        runId=run_id,
        taskId=task_id,
        runKind=run_kind,
        userId=user_id,
        novelId=novel_id,
        chapterId=str(chapter_id) if chapter_id is not None else None,
        startedAt=started_at,
        endedAt=ended_at,
        status="日志尾部损坏" if tail_damaged else trusted_status,
    )


def _required_metadata_text(metadata: dict[str, Any], field: str) -> str | None:
    value = metadata.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _ensure_v2_log(path: Path, *, expected_run_id: str) -> list[_LogFrame]:
    if _is_v2_log(path):
        scan = _scan_v2_frames(path, include_content=False)
        if scan.error is None:
            return _validated_v2_frames(scan.frames, expected_run_id=expected_run_id)
        recovered_frames = _recover_v2_tail(path, scan)
        return _validated_v2_frames(
            recovered_frames,
            expected_run_id=expected_run_id,
        )
    legacy_content = _read_utf8_exact(path)
    summary = _legacy_summary(legacy_content)
    if summary is None:
        raise ValueError("旧版人工日志缺少有效运行信息")
    if summary.runId != expected_run_id:
        raise ValueError("人工日志运行元数据与当前运行不一致")
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
                "trust": "unverified",
            },
            content=legacy_content,
        ),
    ]
    _replace_with_v2_log(path, frames)
    return frames


def _validated_v2_frames(
    frames: list[_LogFrame],
    *,
    expected_run_id: str,
) -> list[_LogFrame]:
    summary = _v2_summary(frames)
    if summary is None:
        raise ValueError("人工日志缺少完整有效的运行元数据")
    if summary.runId != expected_run_id:
        raise ValueError("人工日志运行元数据与当前运行不一致")
    return frames


def _next_sequence(frames: list[_LogFrame], frame_type: str) -> int:
    sequence = sum(1 for frame in frames if frame.header.get("type") == frame_type)
    return sequence + 1


def _is_v2_log(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(_LOG_MAGIC)) == _LOG_MAGIC


def _read_v2_frames(path: Path, *, include_content: bool) -> list[_LogFrame]:
    scan = _scan_v2_frames(path, include_content=include_content)
    if scan.error is not None:
        raise ValueError(scan.error)
    return scan.frames


def _scan_v2_frames(path: Path, *, include_content: bool) -> _FrameScan:
    frames: list[_LogFrame] = []
    source = path.read_bytes()
    handle = BytesIO(source)
    if handle.read(len(_LOG_MAGIC)) != _LOG_MAGIC:
        return _damaged_scan(frames, source, 0, "人工日志版本标识无效")
    last_good_offset = len(_LOG_MAGIC)
    while marker := handle.readline():
        frame_offset = last_good_offset
        try:
            match = _FRAME_PREFIX_PATTERN.fullmatch(marker)
            if match is None:
                raise ValueError("人工日志帧头无效")
            header_length = int(match.group(1))
            content_length = int(match.group(2))
            header_bytes = _read_exact(handle, header_length)
            if handle.read(1) != b"\n":
                raise ValueError("人工日志结构头边界无效")
            content_bytes = _read_exact(handle, content_length)
            decoded_content = content_bytes.decode("utf-8")
            content = decoded_content if include_content else None
            if handle.read(1) != b"\n":
                raise ValueError("人工日志正文边界无效")
            try:
                header = json.loads(header_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("人工日志结构头不是有效 JSON") from exc
            if not isinstance(header, dict) or not isinstance(header.get("type"), str):
                raise ValueError("人工日志结构头字段无效")
            frames.append(_LogFrame(header=header, content=content))
            last_good_offset = handle.tell()
        except (UnicodeDecodeError, ValueError) as exc:
            return _damaged_scan(frames, source, frame_offset, str(exc))
    return _FrameScan(
        frames=frames,
        source=source,
        last_good_offset=last_good_offset,
        tail=b"",
        error=None,
    )


def _damaged_scan(
    frames: list[_LogFrame],
    source: bytes,
    last_good_offset: int,
    error: str,
) -> _FrameScan:
    return _FrameScan(
        frames=frames,
        source=source,
        last_good_offset=last_good_offset,
        tail=source[last_good_offset:],
        error=error,
    )


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    value = handle.read(length)
    if len(value) != length:
        raise ValueError("人工日志帧不完整")
    return value


def _read_utf8_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _render_v2_log(path: Path) -> str:
    scan = _scan_v2_frames(path, include_content=True)
    sections = [
        _legacy_display(frame.content or "")
        if frame.header.get("type") == "legacy"
        else (frame.content or "")
        for frame in scan.frames
    ]
    if scan.error is not None:
        sections.append(
            "\n人工日志尾部损坏：只展示最后一个完整可信帧之前的内容；"
            "下一次写入会先隔离原始残缺字节再恢复。\n"
        )
    return "".join(sections)


def _create_v2_log(path: Path, first_frame: _LogFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_LOG_MAGIC + _encode_frame(first_frame))
        handle.flush()
        os.fsync(handle.fileno())


def _replace_with_v2_log(path: Path, frames: list[_LogFrame]) -> None:
    content = _LOG_MAGIC + b"".join(_encode_frame(frame) for frame in frames)
    _atomic_replace_bytes(path, content)


def _append_frame(path: Path, frame: _LogFrame) -> None:
    with path.open("ab") as handle:
        handle.write(_encode_frame(frame))
        handle.flush()
        os.fsync(handle.fileno())


def _recover_v2_tail(path: Path, scan: _FrameScan) -> list[_LogFrame]:
    if not scan.tail or scan.error is None:
        return scan.frames
    if _v2_summary(scan.frames) is None:
        raise ValueError("人工日志缺少可识别的完整运行信息，不能自动恢复")

    digest = hashlib.sha256(scan.tail).hexdigest()
    recovery_path = path.with_name(
        f"{path.stem}.recovery-{digest}-{len(scan.tail)}.bin"
    )
    if recovery_path.exists():
        if recovery_path.read_bytes() != scan.tail:
            raise ValueError("人工日志残缺尾部隔离文件冲突")
    else:
        _atomic_replace_bytes(recovery_path, scan.tail)

    recovery_frame = _LogFrame(
        header={
            "type": "recovery",
            "fileName": recovery_path.name,
            "sha256": digest,
            "byteLength": len(scan.tail),
            "reason": scan.error,
        },
        content=(
            "\n人工日志尾部损坏已隔离恢复\n"
            f"隔离文件：{recovery_path.name}\n"
            f"SHA-256：{digest}\n"
            f"字节长度：{len(scan.tail)}\n"
        ),
    )
    restored = scan.source[: scan.last_good_offset] + _encode_frame(recovery_frame)
    _atomic_replace_bytes(path, restored)
    return [*scan.frames, recovery_frame]


def _atomic_replace_bytes(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
