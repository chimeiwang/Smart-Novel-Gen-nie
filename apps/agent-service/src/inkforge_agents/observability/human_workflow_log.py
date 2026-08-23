from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, BinaryIO

from ..runtime.model_runtime import ModelCallLogRecord

_LOG_MAGIC = b"INKFORGE-HUMAN-LOG/2\n"
_FRAME_PREFIX_PATTERN = re.compile(rb"INKFORGE-FRAME ([0-9]+) ([0-9]+)\n")
_MAX_FRAME_MARKER_BYTES = 128
_MAX_FRAME_HEADER_BYTES = 64 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024


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
    last_good_offset: int
    file_size: int
    error: str | None


@dataclass(frozen=True, slots=True)
class _ExpectedRunIdentity:
    run_id: str
    task_id: str | None = None
    user_id: str | None = None
    novel_id: str | None = None
    chapter_id: str | None = None
    validate_chapter: bool = False


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
            frames = _ensure_v2_log(
                path,
                expected_identity=_ExpectedRunIdentity(
                    run_id=run_id,
                    task_id=task_id,
                    user_id=user_id,
                    novel_id=novel_id,
                    chapter_id=chapter_id,
                    validate_chapter=True,
                ),
            )
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
            frames = _ensure_v2_log(
                path,
                expected_identity=_ExpectedRunIdentity(run_id=run_id),
            )
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
            frames = _ensure_v2_log(
                path,
                expected_identity=_ExpectedRunIdentity(
                    run_id=record.context.runId,
                    task_id=record.context.taskId,
                    user_id=record.context.userId,
                    novel_id=record.context.novelId,
                ),
            )
            sequence = _next_sequence(frames, "model")
            billing_request_id = record.billingRequestId or "无"
            usage = record.usage
            sections = [
                f"\nA{sequence:02d} 智能体：{record.context.agentId}",
                f"任务标识：{record.context.taskId}",
                f"运行标识：{record.context.runId}",
                f"计费请求标识：{billing_request_id}",
                f"模型：{record.provider}/{record.model}",
                f"policyId：{record.policyId}",
                f"思考模式：{record.thinkingMode}",
                "推理强度："
                + (record.reasoningEffort if record.reasoningEffort is not None else "未设置"),
                "推理 Token："
                + (str(record.reasoningTokens) if record.reasoningTokens is not None else "未提供"),
                "缓存未命中 Token："
                + (
                    str(record.promptCacheMissTokens)
                    if record.promptCacheMissTokens is not None
                    else "未提供"
                ),
                "供应商响应标识："
                + (
                    record.providerResponseId
                    if record.providerResponseId is not None
                    else "未提供"
                ),
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
                    header={
                        "type": "model",
                        "sequence": sequence,
                        "policyId": record.policyId,
                        "thinkingMode": record.thinkingMode,
                        "reasoningEffort": record.reasoningEffort,
                        "reasoningTokens": record.reasoningTokens,
                        "promptCacheMissTokens": record.promptCacheMissTokens,
                        "providerResponseId": record.providerResponseId,
                    },
                    content="\n".join(sections),
                ),
            )

    def finish_run(self, run_id: str, status: str) -> Path:
        with self._lock:
            path = self._require_path(run_id)
            _ensure_v2_log(
                path,
                expected_identity=_ExpectedRunIdentity(run_id=run_id),
            )
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
        except (OSError, OverflowError, UnicodeError, ValueError):
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


def _ensure_v2_log(
    path: Path,
    *,
    expected_identity: _ExpectedRunIdentity,
) -> list[_LogFrame]:
    if _is_v2_log(path):
        scan = _scan_v2_frames(path, include_content=False)
        validated_frames = _validated_v2_frames(
            scan.frames,
            expected_identity=expected_identity,
        )
        if scan.error is None:
            return validated_frames
        recovered_frames = _recover_v2_tail(path, scan)
        return _validated_v2_frames(
            recovered_frames,
            expected_identity=expected_identity,
        )
    legacy_content = _read_utf8_exact(path)
    summary = _legacy_summary(legacy_content)
    if summary is None:
        raise ValueError("旧版人工日志缺少有效运行信息")
    _validate_summary_identity(summary, expected_identity)
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
    expected_identity: _ExpectedRunIdentity,
) -> list[_LogFrame]:
    summary = _v2_summary(frames)
    if summary is None:
        raise ValueError("人工日志缺少完整有效的运行元数据")
    _validate_summary_identity(summary, expected_identity)
    return frames


def _validate_summary_identity(
    summary: WorkflowRunSummary,
    expected: _ExpectedRunIdentity,
) -> None:
    if summary.runId != expected.run_id:
        raise ValueError("人工日志运行元数据与当前运行不一致")
    mismatched = (
        (expected.task_id is not None and summary.taskId != expected.task_id)
        or (expected.user_id is not None and summary.userId != expected.user_id)
        or (expected.novel_id is not None and summary.novelId != expected.novel_id)
        or (expected.validate_chapter and summary.chapterId != expected.chapter_id)
    )
    if mismatched:
        raise ValueError("人工日志运行元数据与当前调用身份不一致")


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
    with path.open("rb") as handle:
        file_size = os.fstat(handle.fileno()).st_size
        if handle.read(len(_LOG_MAGIC)) != _LOG_MAGIC:
            return _damaged_scan(frames, file_size, 0, "人工日志版本标识无效")
        last_good_offset = len(_LOG_MAGIC)
        while handle.tell() < file_size:
            frame_offset = last_good_offset
            try:
                marker = handle.readline(_MAX_FRAME_MARKER_BYTES + 1)
                if not marker.endswith(b"\n") or len(marker) > _MAX_FRAME_MARKER_BYTES:
                    raise ValueError("人工日志帧头超过安全长度或不完整")
                match = _FRAME_PREFIX_PATTERN.fullmatch(marker)
                if match is None:
                    raise ValueError("人工日志帧头无效")
                header_length = int(match.group(1))
                content_length = int(match.group(2))
                if header_length > _MAX_FRAME_HEADER_BYTES:
                    raise ValueError("人工日志结构头超过安全长度")
                if header_length > file_size - handle.tell():
                    raise ValueError("人工日志结构头不完整")
                header_bytes = _read_exact(handle, header_length)
                if handle.read(1) != b"\n":
                    raise ValueError("人工日志结构头边界无效")
                try:
                    header = json.loads(header_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("人工日志结构头不是有效 JSON") from exc
                if not isinstance(header, dict) or not isinstance(
                    header.get("type"), str
                ):
                    raise ValueError("人工日志结构头字段无效")

                content_offset = handle.tell()
                remaining = file_size - content_offset
                if remaining < 1 or content_length > remaining - 1:
                    raise ValueError("人工日志正文不完整")
                if include_content:
                    content = _read_exact(handle, content_length).decode("utf-8")
                else:
                    handle.seek(content_offset + content_length, os.SEEK_SET)
                    content = None
                if handle.read(1) != b"\n":
                    raise ValueError("人工日志正文边界无效")
                frames.append(_LogFrame(header=header, content=content))
                last_good_offset = handle.tell()
            except (OverflowError, UnicodeDecodeError, ValueError) as exc:
                return _damaged_scan(frames, file_size, frame_offset, str(exc))
    return _FrameScan(
        frames=frames,
        last_good_offset=last_good_offset,
        file_size=file_size,
        error=None,
    )


def _damaged_scan(
    frames: list[_LogFrame],
    file_size: int,
    last_good_offset: int,
    error: str,
) -> _FrameScan:
    return _FrameScan(
        frames=frames,
        last_good_offset=last_good_offset,
        file_size=file_size,
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
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(_LOG_MAGIC)
            for frame in frames:
                handle.write(_encode_frame(frame))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _append_frame(path: Path, frame: _LogFrame) -> None:
    with path.open("ab") as handle:
        handle.write(_encode_frame(frame))
        handle.flush()
        os.fsync(handle.fileno())


def _recover_v2_tail(path: Path, scan: _FrameScan) -> list[_LogFrame]:
    tail_length = scan.file_size - scan.last_good_offset
    if tail_length <= 0 or scan.error is None:
        return scan.frames
    if _v2_summary(scan.frames) is None:
        raise ValueError("人工日志缺少可识别的完整运行信息，不能自动恢复")

    recovery_path, digest = _quarantine_tail(
        path,
        start_offset=scan.last_good_offset,
        expected_length=tail_length,
    )
    recovery_frame = _LogFrame(
        header={
            "type": "recovery",
            "fileName": recovery_path.name,
            "sha256": digest,
            "byteLength": tail_length,
            "reason": scan.error,
        },
        content=(
            "\n人工日志尾部损坏已隔离恢复\n"
            f"隔离文件：{recovery_path.name}\n"
            f"SHA-256：{digest}\n"
            f"字节长度：{tail_length}\n"
        ),
    )
    _replace_prefix_with_frame(
        path,
        prefix_length=scan.last_good_offset,
        frame=recovery_frame,
    )
    return [*scan.frames, recovery_frame]


def _quarantine_tail(
    path: Path,
    *,
    start_offset: int,
    expected_length: int,
) -> tuple[Path, str]:
    temporary_path: Path | None = None
    try:
        digest = hashlib.sha256()
        with (
            path.open("rb") as source,
            tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as target,
        ):
            temporary_path = Path(target.name)
            source.seek(start_offset, os.SEEK_SET)
            copied = _copy_exact(source, target.file, expected_length, digest=digest)
            if copied != expected_length:
                raise ValueError("人工日志残缺尾部长度在恢复期间发生变化")
            target.flush()
            os.fsync(target.fileno())
        digest_value = digest.hexdigest()
        recovery_path = path.with_name(
            f"{path.stem}.recovery-{digest_value}-{expected_length}.bin"
        )
        if recovery_path.exists():
            if not _files_equal(temporary_path, recovery_path):
                raise ValueError("人工日志残缺尾部隔离文件冲突")
            temporary_path.unlink()
        else:
            os.replace(temporary_path, recovery_path)
        temporary_path = None
        return recovery_path, digest_value
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _replace_prefix_with_frame(
    path: Path,
    *,
    prefix_length: int,
    frame: _LogFrame,
) -> None:
    temporary_path: Path | None = None
    try:
        with (
            path.open("rb") as source,
            tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as target,
        ):
            temporary_path = Path(target.name)
            copied = _copy_exact(source, target.file, prefix_length)
            if copied != prefix_length:
                raise ValueError("人工日志可信前缀在恢复期间发生变化")
            target.write(_encode_frame(frame))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _copy_exact(
    source: BinaryIO,
    target: IO[bytes],
    length: int,
    *,
    digest: Any | None = None,
) -> int:
    copied = 0
    while copied < length:
        chunk = source.read(min(_COPY_CHUNK_BYTES, length - copied))
        if not chunk:
            break
        target.write(chunk)
        if digest is not None:
            digest.update(chunk)
        copied += len(chunk)
    return copied


def _files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as first_handle, second.open("rb") as second_handle:
        while first_chunk := first_handle.read(_COPY_CHUNK_BYTES):
            if first_chunk != second_handle.read(len(first_chunk)):
                return False
        return second_handle.read(1) == b""


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
