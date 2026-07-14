from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskRecord:
    id: str
    user_id: str
    novel_id: str
    chapter_id: str
    writing_session_id: str | None
    phase: str
    graph_state_json: str | None
