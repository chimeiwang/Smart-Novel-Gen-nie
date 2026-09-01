from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from inkforge_agents.execution.journal import (
    AsyncJournalRedis,
    ExecutionJournalError,
    RedisExecutionJournal,
)
from redis.asyncio import Redis

from .support import (
    execution_request,
    execution_result,
    rehash_request,
)


@pytest.mark.asyncio
async def test_all_execution_journal_lua_runs_on_real_redis(tmp_path) -> None:
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("当前环境没有 redis-server")
    # macOS 的 Unix socket 路径上限很短，pytest 的完整临时目录会超过限制。
    socket_path = Path("/tmp") / f"inkforge-journal-{uuid.uuid4().hex[:12]}.sock"  # noqa: S108 - macOS socket path 长度受限
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
            "--appendonly",
            "yes",
            "--appendfsync",
            "always",
            "--aof-load-truncated",
            "no",
            "--maxmemory",
            "32mb",
            "--maxmemory-policy",
            "noeviction",
            "--hash-max-listpack-value",
            "4096",
            "--hash-max-listpack-entries",
            "64",
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

        journal = RedisExecutionJournal(
            cast(AsyncJournalRedis, redis),
            prefix="real:executions",
            require_durability=True,
        )
        assert (await journal.health()).ready is True
        request = execution_request()
        # 先持久化远大于正常 canary 输出的完整终态，随后证明 delivered 会压成小型 tombstone。
        result = execution_result(request, replacement="改" * 262_144)
        await journal.accept(request, result.resolvedModel.model_dump(mode="json"))
        await journal.mark_started(request)
        assert await journal.begin_provider_attempt(request) == 1
        await journal.record_terminal(request, result)

        quarantine_key = "real:executions:restore:quarantine"
        await redis.set(quarantine_key, "restore-epoch")
        assert await journal.is_restore_quarantined() is True
        assert await journal.claim_callback(request.stepId, force=True) is None
        assert await journal.claim_due_callbacks() == ()
        quarantined = await journal.health()
        assert quarantined.ready is False
        assert quarantined.quarantined is True
        assert quarantined.error_code == "EXECUTION_JOURNAL_RESTORE_QUARANTINED"
        await redis.delete(quarantine_key)
        assert await journal.is_restore_quarantined() is False

        claim = await journal.claim_callback(request.stepId)
        assert claim is not None
        due_at = datetime.now(UTC) + timedelta(seconds=2)
        await journal.reschedule_callback(
            claim,
            error_code="EXECUTION_CALLBACK_UNAVAILABLE",
            next_attempt_at=due_at,
        )
        assert await journal.claim_due_callbacks(now=due_at - timedelta(seconds=1)) == ()
        reclaimed = await journal.claim_due_callbacks(now=due_at)
        assert len(reclaimed) == 1
        await journal.mark_callback_rejected(
            step_id=request.stepId,
            request_hash=request.requestHash,
            result_hash=result.resultHash,
            error_code="EXECUTION_CALLBACK_REJECTED",
            claim_token=reclaimed[0].claim_token,
        )
        key = f"real:executions:{request.stepId}"
        pending_memory = await redis.memory_usage(key, samples=0)
        assert pending_memory is not None
        assert await redis.hstrlen(key, "terminal_payload") > 512 * 1024
        await journal.mark_callback_delivered(
            step_id=request.stepId,
            request_hash=request.requestHash,
            result_hash=result.resultHash,
        )
        delivered_memory = await redis.memory_usage(key, samples=0)
        assert delivered_memory is not None
        assert delivered_memory <= 2 * 1024
        assert delivered_memory * 50 < pending_memory

        refenced = request.model_copy(update={"jobId": "job-2", "fencingToken": 2})
        rebound = await journal.accept(
            refenced,
            result.resolvedModel.model_dump(mode="json"),
        )
        assert rebound.callback_delivery == "delivered"
        assert rebound.terminal is None
        replay_claim = await journal.claim_callback(refenced.stepId)
        assert replay_claim is None

        second = rehash_request(
            execution_request(job_id="job-3").model_copy(
                update={"stepId": "step-2", "idempotencyKey": "idem-2"}
            )
        )
        second_result = execution_result(second)
        await journal.accept(
            second,
            second_result.resolvedModel.model_dump(mode="json"),
        )
        await journal.record_terminal(second, second_result)
        expired = await journal.claim_callback(
            second.stepId,
            now=datetime.now(UTC) - timedelta(seconds=10),
            lease=timedelta(seconds=1),
            force=True,
        )
        assert expired is not None
        recovered = await journal.claim_due_callbacks()
        assert len(recovered) == 1

        await redis.config_set("appendfsync", "everysec")
        unsafe = await journal.health()
        assert unsafe.ready is False
        assert unsafe.persistence_ok is False
        assert unsafe.error_code == "EXECUTION_JOURNAL_PERSISTENCE_UNSAFE"
        with pytest.raises(ExecutionJournalError, match="PERSISTENCE_UNSAFE"):
            await journal.ensure_available()
    finally:
        try:
            await redis.shutdown(nosave=True)
        except Exception:
            process.terminate()
        await redis.aclose()
        process.wait(timeout=5)
