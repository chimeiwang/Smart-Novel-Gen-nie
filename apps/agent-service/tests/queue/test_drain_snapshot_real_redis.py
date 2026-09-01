from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from inkforge_agents.queue.repository import AsyncRedis, QueueJob, RedisRunQueue
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[4]
SNAPSHOT_SCRIPT = (
    ROOT / "scripts/durable_agent_v1_queue_snapshot.lua"
).read_text(encoding="utf-8")
INITIALIZE_SCRIPT = (
    ROOT / "scripts/durable_agent_v1_drain_index_initialize.lua"
).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_v1_queue_producer_and_drain_snapshot_use_only_bounded_index(
    tmp_path: Path,
) -> None:
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("当前环境没有 redis-server")
    socket_path = Path("/tmp") / f"inkforge-queue-{uuid.uuid4().hex[:12]}.sock"  # noqa: S108 - macOS socket path 长度受限
    process = subprocess.Popen(  # noqa: ASYNC220,S603 - 固定本机测试二进制与参数数组
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--save",
            "",
            "--dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    redis = Redis(unix_socket_path=str(socket_path), decode_responses=False)
    try:
        for _ in range(100):
            if socket_path.exists():
                try:
                    if await redis.ping():
                        break
                except OSError:
                    pass
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("真实 Redis 未启动")

        snapshot_script = SNAPSHOT_SCRIPT
        initialize_script = INITIALIZE_SCRIPT
        queue = RedisRunQueue(cast(AsyncRedis, redis), prefix="inkforge:runs")
        created_at = datetime.now(UTC) - timedelta(seconds=2)
        job = QueueJob(
            jobId="large-job",
            kind="writing",
            runId="run-large",
            taskId="task-large",
            novelId="novel-1",
            userId="user-1",
            priority=1,
            payload={"正文": "绝不应被 drain Lua 读取" * 100_000},
            createdAt=created_at,
        )

        assert await queue.enqueue(job) is True
        queued_raw = await redis.eval(snapshot_script, 0)
        assert b"\xe6\xad\xa3\xe6\x96\x87" not in queued_raw
        queued = json.loads(queued_raw)
        assert [entry["id"] for entry in queued["queued"]] == ["large-job"]

        claim = await queue.claim(
            visibility_timeout=timedelta(seconds=1),
            now=created_at + timedelta(seconds=3),
        )
        assert claim is not None
        running = json.loads(await redis.eval(snapshot_script, 0))
        assert [entry["id"] for entry in running["running"]] == ["large-job"]

        assert await queue.retry(
            claim, delay=timedelta(0), now=created_at + timedelta(seconds=3)
        )
        retried = json.loads(await redis.eval(snapshot_script, 0))
        assert [entry["id"] for entry in retried["queued"]] == ["large-job"]

        claim = await queue.claim(
            visibility_timeout=timedelta(seconds=1),
            now=created_at + timedelta(seconds=4),
        )
        assert claim is not None
        assert await queue.defer(
            claim,
            delay=timedelta(milliseconds=1),
            now=created_at + timedelta(seconds=4),
        )
        claim = await queue.claim(
            visibility_timeout=timedelta(seconds=1),
            now=created_at + timedelta(seconds=5),
        )
        assert claim is not None
        assert await queue.recover_expired(
            now=created_at + timedelta(seconds=7)
        ) == 1
        recovered = json.loads(await redis.eval(snapshot_script, 0))
        assert [entry["id"] for entry in recovered["queued"]] == ["large-job"]

        claim = await queue.claim(
            visibility_timeout=timedelta(seconds=1),
            now=created_at + timedelta(seconds=8),
        )
        assert claim is not None
        assert await queue.acknowledge(
            claim, status="completed", now=created_at + timedelta(seconds=8)
        )
        drained = json.loads(await redis.eval(snapshot_script, 0))
        assert drained["queued"] == []
        assert drained["running"] == []

        await redis.delete("inkforge:runs:drain:index-version")
        missing_marker = json.loads(await redis.eval(snapshot_script, 0))
        assert missing_marker == {
            "error": "queue_drain_index_version_missing_or_invalid"
        }
        assert await redis.eval(initialize_script, 0) == b"initialized"
        await redis.set("inkforge:runs:drain:index-version", "0")
        old_marker = json.loads(await redis.eval(snapshot_script, 0))
        assert old_marker == {
            "error": "queue_drain_index_version_missing_or_invalid"
        }

        await redis.flushall()
        await redis.hset("inkforge:runs:statuses", "corrupt", "unknown")
        assert await redis.eval(initialize_script, 0) == b"invalid-status"
        with pytest.raises(RuntimeError, match="drain 索引"):
            await queue.enqueue(job.model_copy(update={"jobId": "after-corruption"}))
        assert await redis.exists("inkforge:runs:drain:index-version") == 0

        await redis.flushall()
        await redis.set("inkforge:runs:drain:index-version", "1")
        await redis.zadd("inkforge:runs:ready", {"orphan": 1})
        orphan = json.loads(await redis.eval(snapshot_script, 0))
        assert orphan == {"error": "queue_drain_index_cardinality_mismatch"}

        await redis.flushall()
        await redis.set("inkforge:runs:drain:index-version", "1")
        mapping = {f"job-{index}": index + 1 for index in range(257)}
        await redis.zadd("inkforge:runs:ready", mapping)
        await redis.zadd("inkforge:runs:drain:queued", mapping)
        await redis.hset(
            "inkforge:runs:statuses",
            mapping={identifier: "queued" for identifier in mapping},
        )
        over_limit = json.loads(await redis.eval(snapshot_script, 0))
        assert over_limit == {"error": "queue_drain_index_resource_limit"}
    finally:
        try:
            await redis.shutdown(nosave=True)
        except Exception:
            process.terminate()
        await redis.aclose()
        process.wait(timeout=5)
