from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import text

from inkforge_core.db.session import create_database_engine
from inkforge_core.writing.job_identity import build_writing_job_id


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    task_id: str
    novel_id: str
    phase: str
    graph_state_sha256: str | None
    updated_at: str
    artifact_keys: tuple[str, ...]
    artifact_count: int
    duplicate_billing_request_ids: tuple[str, ...]
    job_id: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RecoverySnapshot:
        return cls(
            task_id=str(value["task_id"]),
            novel_id=str(value["novel_id"]),
            phase=str(value["phase"]),
            graph_state_sha256=(
                str(value["graph_state_sha256"])
                if value.get("graph_state_sha256") is not None
                else None
            ),
            updated_at=str(value["updated_at"]),
            artifact_keys=_string_tuple(value.get("artifact_keys"), "artifact_keys"),
            artifact_count=int(str(value["artifact_count"])),
            duplicate_billing_request_ids=_string_tuple(
                value.get("duplicate_billing_request_ids"),
                "duplicate_billing_request_ids",
            ),
            job_id=str(value["job_id"]),
        )


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    status: Literal["pass", "pending", "fail"]
    reasons: tuple[str, ...]


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} 必须是列表")
    return tuple(str(item) for item in value)


def evaluate_recovery(
    before: RecoverySnapshot,
    after: RecoverySnapshot,
) -> RecoveryDecision:
    reasons: list[str] = []
    if before.task_id != after.task_id or before.novel_id != after.novel_id:
        reasons.append("恢复前后任务身份不一致")
    if before.graph_state_sha256 is None:
        reasons.append("基线缺少稳定 Graph 状态")
    if after.phase == "error":
        reasons.append("任务进入错误阶段")
    if len(after.artifact_keys) != len(set(after.artifact_keys)):
        reasons.append("产生重复草案键")
    if after.artifact_count > before.artifact_count + 1:
        reasons.append("单次恢复产生多个新草案")
    if after.duplicate_billing_request_ids:
        reasons.append("产生重复计费请求")
    if reasons:
        return RecoveryDecision(status="fail", reasons=tuple(reasons))

    if after.phase in {"idle", "active", "waiting_call"}:
        return RecoveryDecision(status="pending", reasons=())

    progressed = (
        after.updated_at > before.updated_at
        or after.graph_state_sha256 != before.graph_state_sha256
        or after.artifact_count > before.artifact_count
    )
    if not progressed:
        return RecoveryDecision(status="fail", reasons=("任务重启后没有状态推进",))
    if after.phase not in {"awaiting_user_review", "completed"}:
        return RecoveryDecision(status="fail", reasons=("任务恢复到了非预期阶段",))
    return RecoveryDecision(status="pass", reasons=())


async def collect_snapshot(task_id: str, database_url: str) -> RecoverySnapshot:
    engine = create_database_engine(database_url)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                task = (
                    await connection.execute(
                        text(
                            'SELECT "novelId", phase::text AS phase, "graphStateJson", '
                            '"createdAt", "updatedAt" FROM public."WritingTask" '
                            'WHERE id = :task_id'
                        ),
                        {"task_id": task_id},
                    )
                ).mappings().one_or_none()
                if task is None:
                    raise RuntimeError("找不到待验证的写作任务")

                artifacts = (
                    await connection.execute(
                        text(
                            'SELECT "artifactKey" FROM public."ReviewArtifact" '
                            'WHERE "taskId" = :task_id ORDER BY "createdAt", id'
                        ),
                        {"task_id": task_id},
                    )
                ).scalars().all()
                duplicate_billing = (
                    await connection.execute(
                        text(
                            'SELECT "requestId" FROM public."CreditLedger" '
                            'WHERE "novelId" = :novel_id AND type = \'ai_charge\' '
                            'AND "createdAt" >= :created_at GROUP BY "requestId" '
                            'HAVING count(*) > 1 ORDER BY "requestId"'
                        ),
                        {
                            "novel_id": str(task["novelId"]),
                            "created_at": task["createdAt"],
                        },
                    )
                ).scalars().all()
    finally:
        await engine.dispose()

    graph_state = task["graphStateJson"]
    return RecoverySnapshot(
        task_id=task_id,
        novel_id=str(task["novelId"]),
        phase=str(task["phase"]),
        graph_state_sha256=(
            hashlib.sha256(str(graph_state).encode()).hexdigest()
            if graph_state is not None
            else None
        ),
        updated_at=task["updatedAt"].isoformat(),
        artifact_keys=tuple(str(key) for key in artifacts if key is not None),
        artifact_count=len(artifacts),
        duplicate_billing_request_ids=tuple(
            "<空请求标识>" if request_id is None else str(request_id)
            for request_id in duplicate_billing
        ),
        job_id=build_writing_job_id(
            task_id,
            resume=graph_state is not None,
            graph_state_json=str(graph_state) if graph_state is not None else None,
        ),
    )


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("缺少 DATABASE_URL")
    return value


async def _run(arguments: argparse.Namespace) -> int:
    current = await collect_snapshot(arguments.task_id, _database_url())
    if arguments.command == "job-id":
        print(current.job_id)
        return 0

    output = Path(arguments.output)
    if arguments.command == "snapshot":
        if current.phase not in {"idle", "active", "waiting_call"}:
            raise RuntimeError("恢复演练基线必须是运行中的非终态任务")
        if current.graph_state_sha256 is None:
            raise RuntimeError("恢复演练基线缺少稳定 Graph 状态")
        await asyncio.to_thread(
            output.write_text,
            json.dumps(asdict(current), ensure_ascii=False),
            encoding="utf-8",
        )
        print("恢复演练基线已记录")
        return 0

    baseline_text = await asyncio.to_thread(output.read_text, encoding="utf-8")
    baseline = RecoverySnapshot.from_dict(json.loads(baseline_text))
    decision = evaluate_recovery(baseline, current)
    if decision.status == "pass":
        print("恢复演练检查通过")
        return 0
    if decision.status == "pending":
        print("pending：任务仍在运行")
        return 2
    print("；".join(decision.reasons))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 重启恢复只读审计")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("snapshot", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--task-id", required=True)
        command_parser.add_argument("--output", required=True)
    job_id_parser = subparsers.add_parser("job-id")
    job_id_parser.add_argument("--task-id", required=True)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
