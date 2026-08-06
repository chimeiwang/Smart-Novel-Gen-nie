from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class RagJobIdentity:
    task_id: str
    run_id: str


def build_rag_job_identity(
    reference_id: str,
    content_hash: str,
    generation: datetime,
) -> RagJobIdentity:
    task_digest = hashlib.sha256(
        f"rag:{reference_id}:{content_hash}".encode()
    ).hexdigest()[:32]
    generation_utc = (
        generation.replace(tzinfo=UTC)
        if generation.tzinfo is None
        else generation.astimezone(UTC)
    )
    generation_text = generation_utc.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    run_digest = hashlib.sha256(
        f"rag:{reference_id}:{content_hash}:{generation_text}".encode()
    ).hexdigest()[:32]
    return RagJobIdentity(
        task_id=f"rag-{task_digest}",
        run_id=f"rag-{run_digest}",
    )
