"""迁移前只读执行快照；不创建或声称已初始化 V2 drain 索引。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from durable_agent_joint_drain import (
    POSTGRES_METRICS,
    _format_instant,
    _postgres_source,
    _runtime_topology,
    _wal_lsn,
)

UTC = timezone.utc  # noqa: UP017 - 运维入口必须兼容服务器 Python 3.10。


def build(database, runtime_before, postgres_before, ordinary, execution,
          postgres_after, runtime_after):
    before_runtime = _runtime_topology(runtime_before, "迁移前运行身份 PG1")
    after_runtime = _runtime_topology(runtime_after, "迁移前运行身份 PG2")
    core = before_runtime["core"]
    if (before_runtime != after_runtime or core["schemaReady"] is not False
            or core["routeMode"] != "off" or core["v1FreshStartsEnabled"] is not False):
        raise ValueError("运行实例不稳定或两个新建入口未关闭")
    v1_names = {name for name in POSTGRES_METRICS if name.startswith("v1")}
    sources = []
    for raw, label in ((postgres_before, "迁移前 PG1"), (postgres_after, "迁移前 PG2")):
        if set(raw["metrics"]) != v1_names:
            raise ValueError("不是精确的迁移前 PostgreSQL 快照")
        # 调用方已两次验证 unmigrated；缺少 V2 结构意味着尚不存在 V2 行，不是迁移成功。
        normalized = {**raw, "metrics": {**raw["metrics"], **{
            name: [] for name in POSTGRES_METRICS - v1_names
        }}}
        sources.append(_postgres_source(normalized, database, label))
    before, after = sources
    if (before[1] != after[1] or before[4] != after[4]
            or not timedelta(0) <= after[0] - before[0] <= timedelta(seconds=30)
            or _wal_lsn(after[3], "PG2 WAL")[1] < _wal_lsn(before[3], "PG1 WAL")[1]):
        raise ValueError("迁移前 PostgreSQL 身份或阻断集合不稳定")
    observed = []
    for source, kind, counts in (
        (ordinary, "redis", {"queued", "running", "activeStatuses"}),
        (execution, "executionRedis", {"active", "pending", "leased", "rejected"}),
    ):
        expected = counts | {"sourceVersion", "redisRunId", "observedAtMs"}
        if kind == "executionRedis":
            expected.add("quarantined")
        if (set(source) != expected or source["sourceVersion"] != "2"
                or source["redisRunId"] != before_runtime[kind]["redisRunId"]
                or any(type(source[name]) is not int or source[name] != 0 for name in counts)
                or source.get("quarantined", False) is not False):
            raise ValueError("迁移前真实 Redis 仍有执行、回调或异常来源")
        instant = datetime.fromtimestamp(int(source["observedAtMs"]) / 1000, tz=UTC)
        if not before[0] - timedelta(seconds=1) <= instant <= after[0] + timedelta(seconds=1):
            raise ValueError("迁移前 Redis 快照超出稳定窗口")
        observed.append(instant)
    metrics = before[4]
    for name in (
        "v1AgentJobsQueued", "v1AgentJobsOrCallbacksRunning", "v2ExecutionsActive",
        "v2CallbacksPending", "v2CallbacksLeased", "v2CallbacksRejected",
    ):
        metrics[name] = {"count": 0}
    return {
        "schema": "inkforge.pre-migration-execution-drain", "schemaVersion": 1,
        "schemaState": "unmigrated", "database": database, "coreRuntime": core,
        "v2PostgresFacts": "absent-by-verified-schema", "redisIndexes": None,
        "sampleWindow": {
            "startedAt": _format_instant(before[0]), "finishedAt": _format_instant(after[0]),
            "ordinaryRedisAt": _format_instant(observed[0]),
            "executionRedisAt": _format_instant(observed[1]),
        },
        "postgres": {"identity": before[1]}, "metrics": metrics,
    }


def main():
    if len(sys.argv) != 8 or sys.argv[1] not in {"novelwriterdev", "novelwriter"}:
        raise ValueError("迁移前快照参数无效")
    values = [json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[2:]]
    print(json.dumps(build(sys.argv[1], *values), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("迁移前联合执行快照无法证明稳定关闭边界", file=sys.stderr)
        sys.exit(1)
