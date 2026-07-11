from __future__ import annotations

import hashlib


def build_writing_job_id(
    task_id: str,
    *,
    resume: bool,
    graph_state_json: str | None,
) -> str:
    fingerprint = graph_state_json or "initial"
    digest = hashlib.sha256(
        f"writing:{task_id}:{resume}:{fingerprint}".encode()
    ).hexdigest()[:32]
    return f"writing-{digest}"
