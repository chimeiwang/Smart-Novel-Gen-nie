from __future__ import annotations

from typing import Any, Protocol


class WorkflowLogPort(Protocol):
    def start_run(
        self,
        *,
        run_id: str,
        task_id: str,
        run_kind: str,
        user_id: str,
        novel_id: str,
        chapter_id: str | None,
    ) -> object: ...

    def record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None: ...

    def finish_run(self, run_id: str, status: str) -> object: ...
