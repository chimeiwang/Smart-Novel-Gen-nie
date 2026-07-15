from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
                self._append(path, "运行信息：" + _json(metadata) + "\n")
            content = path.read_text(encoding="utf-8")
            run_number = len(re.findall(r"(?m)^R\d{2} ", content)) + 1
            self._append(
                path,
                f"\nR{run_number:02d} {run_kind}\n开始时间：{timestamp}\n",
            )
            self._paths[run_id] = path
            return path

    def record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        with self._lock:
            path = self._require_path(run_id)
            content = path.read_text(encoding="utf-8")
            sequence = len(re.findall(r"(?m)^S\d{3} 状态切换$", content)) + 1
            self._append(
                path,
                f"\nS{sequence:03d} 状态切换\n节点：{node}\n字段：{_json(changes)}\n",
            )

    def record_model_call(
        self,
        run_id: str,
        agent_id: str,
        messages: list[dict[str, Any]],
        output: str,
        finish_reason: str,
        raw_finish_reason: str | None,
    ) -> None:
        with self._lock:
            path = self._require_path(run_id)
            content = path.read_text(encoding="utf-8")
            sequence = len(re.findall(r"(?m)^A\d{2} 智能体：", content)) + 1
            sections = [f"\nA{sequence:02d} 智能体：{agent_id}", "请求消息："]
            for message in messages:
                role = _role_label(message.get("role"))
                value = message.get("content")
                sections.extend((f"[{role}]", value if isinstance(value, str) else _json(value)))
            sections.extend(
                (
                    "模型响应：",
                    output,
                    f"完成原因：{finish_reason}",
                    f"供应商原始原因：{raw_finish_reason or '未提供'}",
                    "",
                )
            )
            self._append(path, "\n".join(sections))

    def finish_run(self, run_id: str, status: str) -> Path:
        with self._lock:
            path = self._require_path(run_id)
            self._append(path, f"结束时间：{_now()}\n结束状态：{status}\n")
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
            return WorkflowLogDetail(summary=summary, content=path.read_text(encoding="utf-8"))

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
        content = path.read_text(encoding="utf-8")
        first_line = content.splitlines()[0] if content else ""
        if not first_line.startswith("运行信息："):
            return None
        try:
            metadata = json.loads(first_line.removeprefix("运行信息："))
        except json.JSONDecodeError:
            return None
        run_kinds = re.findall(r"(?m)^R\d{2} (.+)$", content)
        ended = re.findall(r"(?m)^结束时间：(.+)$", content)
        statuses = re.findall(r"(?m)^结束状态：(.+)$", content)
        return WorkflowRunSummary(
            runId=str(metadata["runId"]),
            taskId=str(metadata["taskId"]),
            runKind=run_kinds[-1] if run_kinds else "未知运行",
            userId=str(metadata["userId"]),
            novelId=str(metadata["novelId"]),
            chapterId=(
                str(metadata["chapterId"])
                if metadata.get("chapterId") is not None
                else None
            ),
            startedAt=str(metadata["startedAt"]),
            endedAt=ended[-1] if ended else str(metadata["startedAt"]),
            status=statuses[-1] if statuses else "执行中",
        )

    @staticmethod
    def _append(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(content)


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
