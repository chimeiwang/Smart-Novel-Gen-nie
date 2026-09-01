#!/usr/bin/env python3
"""构建并复验不含业务正文或凭据的 V1/V2 联合 drain 稳定窗口。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

SCHEMA = "inkforge.durable-agent-joint-drain"
SCHEMA_VERSION = "2"
MAX_INPUT_BYTES = 1_048_576
MAX_IDENTIFIER_LENGTH = 512
MAX_ENTRIES_PER_SOURCE = 256
MAX_POSTGRES_ENTRIES = 4_096
MAX_WINDOW_MILLIS = 30_000
REDIS_CLOCK_TOLERANCE = timedelta(seconds=1)

POSTGRES_METRICS = {
    "v1WritingTasksActive",
    "v1WritingTasksAwaitingUser",
    "v1WritingTasksRecoverable",
    "v1CommandsActive",
    "v1OutboxUndelivered",
    "v1ArtifactsAwaitingUser",
    "v1ArtifactsRecoverable",
    "v2RunsActive",
    "v2StepsActive",
    "v2BillingReserved",
    "v2BillingReconciliationRequired",
}
V1_REDIS_METRICS = {
    "v1AgentJobsQueued",
    "v1AgentJobsOrCallbacksRunning",
}
V2_REDIS_METRICS = {
    "v2ExecutionsActive",
    "v2CallbacksPending",
    "v2CallbacksLeased",
    "v2CallbacksRejected",
}
V1_METRICS = {
    metric
    for metric in POSTGRES_METRICS | V1_REDIS_METRICS
    if metric.startswith("v1")
}
V2_METRICS = {
    metric
    for metric in POSTGRES_METRICS | V2_REDIS_METRICS
    if metric.startswith("v2")
}
ALL_METRICS = V1_METRICS | V2_METRICS
REPORT_KEYS = {
    "schema",
    "schemaVersion",
    "database",
    "coreRuntime",
    "sampleWindow",
    "postgres",
    "redisIndexes",
    "runtimeTopologySha256",
    "v1DrainZero",
    "v2Converged",
    "metrics",
}
HEX_64 = re.compile(r"[0-9a-f]{64}")
CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}")
REDIS_RUN_ID = re.compile(r"[0-9a-f]{40}")
WAL_LSN = re.compile(r"[0-9A-F]+/[0-9A-F]+")


class DrainStatusInvalid(ValueError):
    """输入来源不能形成可信联合状态。"""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DrainStatusInvalid(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def _read_json(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise DrainStatusInvalid("快照文件不是普通文件")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise DrainStatusInvalid("快照文件超过大小上限")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda raw: (_ for _ in ()).throw(
                DrainStatusInvalid(f"JSON 包含非法数字：{raw}")
            ),
        )
    except DrainStatusInvalid:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DrainStatusInvalid("快照不是有效 UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DrainStatusInvalid("快照顶层必须是对象")
    if "error" in value:
        error = value.get("error")
        if isinstance(error, str) and re.fullmatch(r"[a-z0-9_]{1,96}", error):
            raise DrainStatusInvalid(f"来源封闭失败：{error}")
        raise DrainStatusInvalid("来源返回无效错误")
    return value


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DrainStatusInvalid(f"{label} 字段集合无效")
    return value


def _text(value: Any, label: str, *, maximum: int = MAX_IDENTIFIER_LENGTH) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise DrainStatusInvalid(f"{label} 不是安全非空字符串")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise DrainStatusInvalid(f"{label} 必须是布尔值")
    return value


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DrainStatusInvalid(f"{label} 必须是非负整数")
    return cast(int, value)


def _instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DrainStatusInvalid(f"{label} 必须是带时区时间")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DrainStatusInvalid(f"{label} 时间格式无效") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DrainStatusInvalid(f"{label} 缺少时区")
    return parsed.astimezone(UTC)


def _millis(value: Any, label: str) -> datetime:
    text = _text(value, label, maximum=20)
    if not text.isdigit():
        raise DrainStatusInvalid(f"{label} 必须是 epoch 毫秒")
    try:
        return datetime.fromtimestamp(int(text) / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise DrainStatusInvalid(f"{label} 超出时间范围") from exc


def _format_instant(value: datetime) -> str:
    milliseconds = value.microsecond // 1000
    return value.strftime("%Y-%m-%dT%H:%M:%S") + f".{milliseconds:03d}Z"


def _wal_lsn(value: Any, label: str) -> tuple[str, int]:
    text = _text(value, label, maximum=64)
    if WAL_LSN.fullmatch(text) is None:
        raise DrainStatusInvalid(f"{label} 无效")
    upper, lower = text.split("/", 1)
    return text, (int(upper, 16) << 32) + int(lower, 16)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _metric(entries: list[tuple[datetime, str]]) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: (item[0], item[1]))
    oldest_at, oldest_id = ordered[0] if ordered else (None, None)
    canonical_entries = [
        {"id": identifier, "at": _format_instant(observed_at)}
        for observed_at, identifier in ordered
    ]
    return {
        "count": len(ordered),
        "oldestId": oldest_id,
        "oldestAt": _format_instant(oldest_at) if oldest_at is not None else None,
        "setSha256": _sha256(canonical_entries),
    }


def _entries(
    value: Any,
    label: str,
    *,
    time_key: str,
    millis: bool = False,
    maximum: int = MAX_ENTRIES_PER_SOURCE,
) -> list[tuple[datetime, str]]:
    if not isinstance(value, list) or len(value) > maximum:
        raise DrainStatusInvalid(f"{label} 必须是有界数组")
    entries: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(value):
        entry = _exact_object(raw_entry, {"id", time_key}, f"{label}[{index}]")
        identifier = _text(entry["id"], f"{label}[{index}].id")
        if identifier in seen:
            raise DrainStatusInvalid(f"{label} 包含重复 ID")
        seen.add(identifier)
        observed_at = (
            _millis(entry[time_key], f"{label}[{index}].{time_key}")
            if millis
            else _instant(entry[time_key], f"{label}[{index}].{time_key}")
        )
        entries.append((observed_at, identifier))
    return entries


def _postgres_source(
    raw: dict[str, Any], expected_database: str, label: str
) -> tuple[
    datetime,
    dict[str, Any],
    str,
    str,
    dict[str, dict[str, Any]],
]:
    source = _exact_object(
        raw,
        {
            "sourceVersion",
            "database",
            "identity",
            "observedAt",
            "snapshot",
            "walLsn",
            "metrics",
        },
        label,
    )
    if source["sourceVersion"] != "2" or source["database"] != expected_database:
        raise DrainStatusInvalid(f"{label} 版本或数据库身份不一致")
    identity = _exact_object(
        source["identity"],
        {"databaseOid", "serverAddress", "serverPort", "serverVersionNum"},
        f"{label}.identity",
    )
    database_oid = _non_negative_integer(identity["databaseOid"], "databaseOid")
    server_port = _non_negative_integer(identity["serverPort"], "serverPort")
    server_version = _non_negative_integer(
        identity["serverVersionNum"], "serverVersionNum"
    )
    normalized_identity = {
        "databaseOid": database_oid,
        "serverAddress": _text(identity["serverAddress"], "serverAddress"),
        "serverPort": server_port,
        "serverVersionNum": server_version,
    }
    snapshot = _text(source["snapshot"], f"{label}.snapshot", maximum=256)
    wal_lsn, _wal_lsn_value = _wal_lsn(source["walLsn"], f"{label}.walLsn")
    raw_metrics = _exact_object(source["metrics"], POSTGRES_METRICS, f"{label}.metrics")
    metrics = {
        name: _metric(
            _entries(
                value,
                f"{label}.{name}",
                time_key="at",
                maximum=MAX_POSTGRES_ENTRIES,
            )
        )
        for name, value in raw_metrics.items()
    }
    return (
        _instant(source["observedAt"], f"{label}.observedAt"),
        normalized_identity,
        snapshot,
        wal_lsn,
        metrics,
    )


def _redis_identity(source: dict[str, Any], label: str) -> tuple[datetime, str, str]:
    if source["sourceVersion"] != "2" or source["indexVersion"] != "1":
        raise DrainStatusInvalid(f"{label} source/index version 无效")
    run_id = _text(source["redisRunId"], f"{label}.redisRunId", maximum=40)
    if REDIS_RUN_ID.fullmatch(run_id) is None:
        raise DrainStatusInvalid(f"{label}.redisRunId 无效")
    return (
        _millis(source["observedAtMs"], f"{label}.observedAtMs"),
        source["indexVersion"],
        run_id,
    )


def _ordinary_redis_source(
    raw: dict[str, Any],
) -> tuple[datetime, str, str, dict[str, dict[str, Any]]]:
    source = _exact_object(
        raw,
        {
            "sourceVersion",
            "indexVersion",
            "redisRunId",
            "observedAtMs",
            "queued",
            "running",
        },
        "普通 Redis 快照",
    )
    observed_at, version, run_id = _redis_identity(source, "普通 Redis")
    queued = _entries(source["queued"], "queued", time_key="createdAtMs", millis=True)
    running = _entries(
        source["running"], "running", time_key="createdAtMs", millis=True
    )
    if len(queued) + len(running) > MAX_ENTRIES_PER_SOURCE:
        raise DrainStatusInvalid("普通 Redis active 索引超过上限")
    return observed_at, version, run_id, {
        "v1AgentJobsQueued": _metric(queued),
        "v1AgentJobsOrCallbacksRunning": _metric(running),
    }


def _execution_redis_source(
    raw: dict[str, Any],
) -> tuple[datetime, str, str, dict[str, dict[str, Any]]]:
    source = _exact_object(
        raw,
        {
            "sourceVersion",
            "indexVersion",
            "redisRunId",
            "observedAtMs",
            "active",
            "pending",
            "leased",
            "rejected",
            "quarantined",
        },
        "execution Redis 快照",
    )
    observed_at, version, run_id = _redis_identity(source, "execution Redis")
    if source["quarantined"] is not False:
        raise DrainStatusInvalid("execution Redis restore quarantine 未解除")
    groups = {
        "v2ExecutionsActive": _entries(
            source["active"], "active", time_key="acceptedAtMs", millis=True
        ),
        "v2CallbacksPending": _entries(
            source["pending"], "pending", time_key="acceptedAtMs", millis=True
        ),
        "v2CallbacksLeased": _entries(
            source["leased"], "leased", time_key="acceptedAtMs", millis=True
        ),
        "v2CallbacksRejected": _entries(
            source["rejected"], "rejected", time_key="acceptedAtMs", millis=True
        ),
    }
    all_ids = [identifier for values in groups.values() for _at, identifier in values]
    if len(all_ids) > MAX_ENTRIES_PER_SOURCE or len(all_ids) != len(set(all_ids)):
        raise DrainStatusInvalid("execution Redis active/callback 集合重复或超限")
    return observed_at, version, run_id, {
        name: _metric(entries) for name, entries in groups.items()
    }


def _runtime_topology(raw: dict[str, Any], label: str) -> dict[str, Any]:
    topology = _exact_object(
        raw,
        {"sourceVersion", "core", "redis", "executionRedis"},
        label,
    )
    if topology["sourceVersion"] != "1":
        raise DrainStatusInvalid(f"{label} 版本无效")
    core = _exact_object(
        topology["core"],
        {
            "containerId",
            "imageId",
            "schemaReady",
            "routeMode",
            "v1FreshStartsEnabled",
        },
        f"{label}.core",
    )
    normalized_core = {
        "containerId": _container_id(core["containerId"], f"{label}.core.containerId"),
        "imageId": _image_id(core["imageId"], f"{label}.core.imageId"),
        "schemaReady": _boolean(core["schemaReady"], f"{label}.core.schemaReady"),
        "routeMode": _text(core["routeMode"], f"{label}.core.routeMode", maximum=16),
        "v1FreshStartsEnabled": _boolean(
            core["v1FreshStartsEnabled"], f"{label}.core.v1FreshStartsEnabled"
        ),
    }
    services: dict[str, Any] = {"core": normalized_core}
    for name in ("redis", "executionRedis"):
        service = _exact_object(
            topology[name],
            {"containerId", "imageId", "redisRunId"},
            f"{label}.{name}",
        )
        run_id = _text(service["redisRunId"], f"{label}.{name}.redisRunId", maximum=40)
        if REDIS_RUN_ID.fullmatch(run_id) is None:
            raise DrainStatusInvalid(f"{label}.{name}.redisRunId 无效")
        services[name] = {
            "containerId": _container_id(
                service["containerId"], f"{label}.{name}.containerId"
            ),
            "imageId": _image_id(service["imageId"], f"{label}.{name}.imageId"),
            "redisRunId": run_id,
        }
    return services


def _container_id(value: Any, label: str) -> str:
    identifier = _text(value, label, maximum=64)
    if CONTAINER_ID.fullmatch(identifier) is None:
        raise DrainStatusInvalid(f"{label} 无效")
    return identifier


def _image_id(value: Any, label: str) -> str:
    identifier = _text(value, label, maximum=71)
    if not identifier.startswith("sha256:") or HEX_64.fullmatch(identifier[7:]) is None:
        raise DrainStatusInvalid(f"{label} 无效")
    return identifier


def build_report(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.database not in {"novelwriterdev", "novelwriter"}:
        raise DrainStatusInvalid("目标数据库无效")
    topology_before = _runtime_topology(_read_json(arguments.runtime_before), "运行拓扑 1")
    postgres_before = _postgres_source(
        _read_json(arguments.postgres_before), arguments.database, "PostgreSQL PG1"
    )
    ordinary = _ordinary_redis_source(_read_json(arguments.ordinary_redis))
    execution = _execution_redis_source(_read_json(arguments.execution_redis))
    postgres_after = _postgres_source(
        _read_json(arguments.postgres_after), arguments.database, "PostgreSQL PG2"
    )
    topology_after = _runtime_topology(_read_json(arguments.runtime_after), "运行拓扑 2")

    if topology_before != topology_after:
        raise DrainStatusInvalid("采样期间运行容器、镜像、Redis 进程或 Core 配置漂移")
    core = topology_before["core"]
    if (
        core["schemaReady"] is not True
        or core["routeMode"] != "off"
        or core["v1FreshStartsEnabled"] is not False
    ):
        raise DrainStatusInvalid("运行 Core 未同时关闭 V1 fresh start 与 V2 route")
    if topology_before["redis"]["redisRunId"] != ordinary[2]:
        raise DrainStatusInvalid("普通 Redis 快照与运行进程身份不一致")
    if topology_before["executionRedis"]["redisRunId"] != execution[2]:
        raise DrainStatusInvalid("execution Redis 快照与运行进程身份不一致")

    before_at, before_identity, before_snapshot, before_lsn, before_metrics = (
        postgres_before
    )
    after_at, after_identity, after_snapshot, after_lsn, after_metrics = postgres_after
    if before_identity != after_identity:
        raise DrainStatusInvalid("PG1/PG2 数据库服务身份漂移")
    if after_at < before_at:
        raise DrainStatusInvalid("PG2 时间早于 PG1")
    if _wal_lsn(after_lsn, "PG2.walLsn")[1] < _wal_lsn(before_lsn, "PG1.walLsn")[1]:
        raise DrainStatusInvalid("PG2 WAL 水位早于 PG1")
    duration_millis = round((after_at - before_at).total_seconds() * 1000)
    if duration_millis > MAX_WINDOW_MILLIS:
        raise DrainStatusInvalid("联合 drain 采样窗口超过 30 秒")
    if before_metrics != after_metrics:
        raise DrainStatusInvalid("PG1/PG2 精确阻断集合发生变化")
    for label, observed_at in (("普通 Redis", ordinary[0]), ("execution Redis", execution[0])):
        if (
            observed_at < before_at - REDIS_CLOCK_TOLERANCE
            or observed_at > after_at + REDIS_CLOCK_TOLERANCE
        ):
            raise DrainStatusInvalid(f"{label} 观察时间不在 PG1/PG2 稳定窗口内")

    metrics = {**before_metrics, **ordinary[3], **execution[3]}
    if set(metrics) != ALL_METRICS:
        raise DrainStatusInvalid("联合 metrics 字段集合无效")
    blocker_hash = _sha256(
        {name: before_metrics[name]["setSha256"] for name in sorted(before_metrics)}
    )
    topology_hash = _sha256(topology_before)
    return {
        "schema": SCHEMA,
        "schemaVersion": SCHEMA_VERSION,
        "database": arguments.database,
        "coreRuntime": core,
        "sampleWindow": {
            "startedAt": _format_instant(before_at),
            "ordinaryRedisAt": _format_instant(ordinary[0]),
            "executionRedisAt": _format_instant(execution[0]),
            "finishedAt": _format_instant(after_at),
            "durationMillis": duration_millis,
        },
        "postgres": {
            "identity": before_identity,
            "beforeSnapshot": before_snapshot,
            "afterSnapshot": after_snapshot,
            "beforeWalLsn": before_lsn,
            "afterWalLsn": after_lsn,
            "blockerSetSha256": blocker_hash,
        },
        "redisIndexes": {"v1Version": ordinary[1], "v2Version": execution[1]},
        "runtimeTopologySha256": topology_hash,
        "v1DrainZero": all(metrics[name]["count"] == 0 for name in V1_METRICS),
        "v2Converged": all(metrics[name]["count"] == 0 for name in V2_METRICS),
        "metrics": {name: metrics[name] for name in sorted(metrics)},
    }


def validate_report(raw: dict[str, Any]) -> dict[str, Any]:
    report = _exact_object(raw, REPORT_KEYS, "联合 drain report")
    if report["schema"] != SCHEMA or report["schemaVersion"] != SCHEMA_VERSION:
        raise DrainStatusInvalid("联合 drain report 版本无效")
    database = _text(report["database"], "database", maximum=32)
    if database not in {"novelwriterdev", "novelwriter"}:
        raise DrainStatusInvalid("联合 drain report 数据库无效")
    core = _exact_object(
        report["coreRuntime"],
        {
            "containerId",
            "imageId",
            "schemaReady",
            "routeMode",
            "v1FreshStartsEnabled",
        },
        "coreRuntime",
    )
    _container_id(core["containerId"], "coreRuntime.containerId")
    _image_id(core["imageId"], "coreRuntime.imageId")
    if (
        core["schemaReady"] is not True
        or core["routeMode"] != "off"
        or core["v1FreshStartsEnabled"] is not False
    ):
        raise DrainStatusInvalid("coreRuntime 未证明两个新建入口关闭")
    window = _exact_object(
        report["sampleWindow"],
        {
            "startedAt",
            "ordinaryRedisAt",
            "executionRedisAt",
            "finishedAt",
            "durationMillis",
        },
        "sampleWindow",
    )
    started = _instant(window["startedAt"], "sampleWindow.startedAt")
    ordinary_at = _instant(window["ordinaryRedisAt"], "sampleWindow.ordinaryRedisAt")
    execution_at = _instant(window["executionRedisAt"], "sampleWindow.executionRedisAt")
    finished = _instant(window["finishedAt"], "sampleWindow.finishedAt")
    duration = _non_negative_integer(window["durationMillis"], "durationMillis")
    if (
        finished < started
        or duration != round((finished - started).total_seconds() * 1000)
        or duration > MAX_WINDOW_MILLIS
    ):
        raise DrainStatusInvalid("sampleWindow 时间关系无效")
    if (
        ordinary_at < started - REDIS_CLOCK_TOLERANCE
        or ordinary_at > finished + REDIS_CLOCK_TOLERANCE
        or execution_at < started - REDIS_CLOCK_TOLERANCE
        or execution_at > finished + REDIS_CLOCK_TOLERANCE
    ):
        raise DrainStatusInvalid("Redis 时间不在稳定窗口")
    postgres = _exact_object(
        report["postgres"],
        {
            "identity",
            "beforeSnapshot",
            "afterSnapshot",
            "beforeWalLsn",
            "afterWalLsn",
            "blockerSetSha256",
        },
        "postgres",
    )
    _exact_object(
        postgres["identity"],
        {"databaseOid", "serverAddress", "serverPort", "serverVersionNum"},
        "postgres.identity",
    )
    _text(postgres["beforeSnapshot"], "beforeSnapshot", maximum=256)
    _text(postgres["afterSnapshot"], "afterSnapshot", maximum=256)
    before_lsn = _wal_lsn(postgres["beforeWalLsn"], "beforeWalLsn")[1]
    after_lsn = _wal_lsn(postgres["afterWalLsn"], "afterWalLsn")[1]
    if after_lsn < before_lsn:
        raise DrainStatusInvalid("afterWalLsn 早于 beforeWalLsn")
    for name in ("blockerSetSha256",):
        if HEX_64.fullmatch(_text(postgres[name], name, maximum=64)) is None:
            raise DrainStatusInvalid(f"{name} 无效")
    indexes = _exact_object(
        report["redisIndexes"], {"v1Version", "v2Version"}, "redisIndexes"
    )
    if indexes != {"v1Version": "1", "v2Version": "1"}:
        raise DrainStatusInvalid("Redis drain index 版本无效")
    if HEX_64.fullmatch(
        _text(report["runtimeTopologySha256"], "runtimeTopologySha256", maximum=64)
    ) is None:
        raise DrainStatusInvalid("runtimeTopologySha256 无效")
    metrics = _exact_object(report["metrics"], ALL_METRICS, "联合 drain metrics")
    normalized: dict[str, dict[str, Any]] = {}
    for name, raw_metric in metrics.items():
        value = _exact_object(
            raw_metric,
            {"count", "oldestId", "oldestAt", "setSha256"},
            f"metric {name}",
        )
        count = _non_negative_integer(value["count"], f"metric {name}.count")
        if HEX_64.fullmatch(
            _text(value["setSha256"], f"metric {name}.setSha256", maximum=64)
        ) is None:
            raise DrainStatusInvalid(f"metric {name}.setSha256 无效")
        if count == 0:
            if value["oldestId"] is not None or value["oldestAt"] is not None:
                raise DrainStatusInvalid(f"metric {name} 的零计数夹带 oldest")
        else:
            _text(value["oldestId"], f"metric {name}.oldestId")
            _instant(value["oldestAt"], f"metric {name}.oldestAt")
        normalized[name] = value
    expected_blocker_hash = _sha256(
        {
            name: normalized[name]["setSha256"]
            for name in sorted(POSTGRES_METRICS)
        }
    )
    if postgres["blockerSetSha256"] != expected_blocker_hash:
        raise DrainStatusInvalid("PostgreSQL blockerSetSha256 与 metrics 不一致")
    expected_v1 = all(normalized[name]["count"] == 0 for name in V1_METRICS)
    expected_v2 = all(normalized[name]["count"] == 0 for name in V2_METRICS)
    if report["v1DrainZero"] is not expected_v1:
        raise DrainStatusInvalid("v1DrainZero 与 metrics 不一致")
    if report["v2Converged"] is not expected_v2:
        raise DrainStatusInvalid("v2Converged 与 metrics 不一致")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--database", required=True)
    build.add_argument("--runtime-before", required=True)
    build.add_argument("--postgres-before", required=True)
    build.add_argument("--ordinary-redis", required=True)
    build.add_argument("--execution-redis", required=True)
    build.add_argument("--postgres-after", required=True)
    build.add_argument("--runtime-after", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--report", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "build":
            print(_canonical(build_report(arguments)))
            return 0
        report = validate_report(_read_json(arguments.report))
        print(_canonical(report))
        return 0 if report["v1DrainZero"] and report["v2Converged"] else 3
    except DrainStatusInvalid as exc:
        print(f"joint-drain-status:invalid:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
