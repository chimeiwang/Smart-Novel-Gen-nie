#!/usr/bin/env python3
"""构建、签发、claim 并封存发布破坏性边界的 live drain 证据。"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from durable_agent_joint_drain import validate_report as validate_joint_report

LIVE_FORMAT = "inkforge-durable-agent-v2-live-drain/1"
EVIDENCE_FORMAT = "inkforge-durable-agent-v2-boundary-evidence/1"
APPLIED_FORMAT = "inkforge-durable-agent-v2-boundary-applied/1"
LEDGER_FORMAT = "inkforge-durable-agent-v2-boundary-ledger/1"
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
BOUNDARY = re.compile(
    r"(?:compose-release|compose-rollback|allowlist-config|ddl-forward-[1-9][0-9]*)\Z"
)
MAX_FILE_BYTES = 1_048_576
MAX_WINDOW = timedelta(seconds=30)
MAX_EVIDENCE_AGE = timedelta(seconds=15)
V1_POSTGRES_METRICS = {
    "v1ArtifactsAwaitingUser",
    "v1ArtifactsRecoverable",
    "v1CommandsActive",
    "v1OutboxUndelivered",
    "v1WritingTasksActive",
    "v1WritingTasksAwaitingUser",
    "v1WritingTasksRecoverable",
}
V2_POSTGRES_METRICS = {
    "v2BillingReconciliationRequired",
    "v2BillingReserved",
    "v2RunsActive",
    "v2StepsActive",
}
EVIDENCE_KEYS = {
    "boundary",
    "boundaryHelperSha256",
    "controlBundleSha256",
    "expiresAt",
    "format",
    "issuedAt",
    "liveDrain",
    "liveDrainSha256",
    "lockId",
    "manifestSha256",
    "runAttempt",
    "runId",
    "sequence",
    "targetReleaseCommit",
    "workflowTrustedCommit",
}


class BoundaryInvalid(ValueError):
    """live drain 或一次性 boundary evidence 无法授权动作。"""


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BoundaryInvalid(f"JSON key 重复：{key}")
        result[key] = value
    return result


def load(path: Path | None) -> tuple[dict[str, Any], bytes]:
    if path is None:
        raise BoundaryInvalid("缺少 profile 所需输入")
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise BoundaryInvalid("边界输入文件无效")
        payload = path.read_bytes()
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=lambda raw: (_ for _ in ()).throw(
                BoundaryInvalid(f"JSON 非法数字：{raw}")
            ),
        )
    except BoundaryInvalid:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BoundaryInvalid("边界输入不是有效 UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise BoundaryInvalid("边界输入顶层必须是对象")
    return value, payload


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise BoundaryInvalid(f"{label} 字段无效")
    return value


def text(value: Any, label: str, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise BoundaryInvalid(f"{label} 无效")
    return value


def hex_value(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise BoundaryInvalid(f"{label} 无效")
    return value


def instant(value: Any, label: str) -> datetime:
    raw = text(value, label, 64)
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise BoundaryInvalid(f"{label} 无效") from error
    if parsed.tzinfo is None:
        raise BoundaryInvalid(f"{label} 缺少时区")
    return parsed.astimezone(UTC)


def image_id(value: Any, label: str) -> str:
    raw = text(value, label, 71)
    if not raw.startswith("sha256:") or HEX_64.fullmatch(raw[7:]) is None:
        raise BoundaryInvalid(f"{label} 无效")
    return raw


def validate_topology(raw: dict[str, Any]) -> dict[str, Any]:
    topology = exact(
        raw,
        {"sourceVersion", "core", "redis", "executionRedis"},
        "runtime topology",
    )
    if topology["sourceVersion"] != "1":
        raise BoundaryInvalid("runtime topology 版本无效")
    core = exact(
        topology["core"],
        {"containerId", "imageId", "schemaReady", "routeMode", "v1FreshStartsEnabled"},
        "Core identity",
    )
    hex_value(core["containerId"], re.compile(r"[0-9a-f]{12,64}\Z"), "Core container")
    image_id(core["imageId"], "Core image")
    if not isinstance(core["schemaReady"], bool) or not isinstance(
        core["v1FreshStartsEnabled"], bool
    ):
        raise BoundaryInvalid("Core 布尔配置无效")
    if core["routeMode"] != "off" or core["v1FreshStartsEnabled"] is not False:
        raise BoundaryInvalid("live drain 要求 route-off 且 V1 fresh=false")
    for name in ("redis", "executionRedis"):
        identity = exact(
            topology[name],
            {"containerId", "imageId", "redisRunId"},
            name,
        )
        hex_value(
            identity["containerId"],
            re.compile(r"[0-9a-f]{12,64}\Z"),
            f"{name} container",
        )
        image_id(identity["imageId"], f"{name} image")
        hex_value(identity["redisRunId"], HEX_40, f"{name} run ID")
    return topology


def validate_pg_source(
    raw: dict[str, Any],
    *,
    expected_database: str,
    expected_metrics: set[str],
) -> tuple[datetime, dict[str, Any]]:
    source = exact(
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
        "PostgreSQL source",
    )
    if source["sourceVersion"] != "2" or source["database"] != expected_database:
        raise BoundaryInvalid("PostgreSQL source 身份无效")
    identity = exact(
        source["identity"],
        {"databaseOid", "serverAddress", "serverPort", "serverVersionNum"},
        "PostgreSQL identity",
    )
    for key, value in identity.items():
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise BoundaryInvalid(f"PostgreSQL identity.{key} 无效")
    text(source["snapshot"], "PostgreSQL snapshot", 256)
    wal_lsn = text(source["walLsn"], "WAL LSN", 64)
    if re.fullmatch(r"[0-9A-F]+/[0-9A-F]+", wal_lsn) is None:
        raise BoundaryInvalid("WAL LSN 无效")
    metrics = exact(source["metrics"], expected_metrics, "PostgreSQL metrics")
    for name, entries in metrics.items():
        if not isinstance(entries, list) or entries:
            raise BoundaryInvalid(f"PostgreSQL blocker 非零：{name}")
    return instant(source["observedAt"], "PostgreSQL observedAt"), identity


def validate_redis_source(
    raw: dict[str, Any],
    *,
    topology: dict[str, Any],
    execution: bool,
) -> datetime:
    arrays = {"active", "pending", "leased", "rejected"} if execution else {
        "queued",
        "running",
    }
    keys = {"sourceVersion", "indexVersion", "redisRunId", "observedAtMs"} | arrays
    if execution:
        keys.add("quarantined")
    source = exact(raw, keys, "Redis source")
    if source["sourceVersion"] != "2" or source["indexVersion"] != "pre-activation":
        raise BoundaryInvalid("Redis pre-activation source 版本无效")
    expected = topology["executionRedis" if execution else "redis"]["redisRunId"]
    if source["redisRunId"] != expected:
        raise BoundaryInvalid("Redis run ID 与 topology 漂移")
    for name in arrays:
        if not isinstance(source[name], list) or source[name]:
            raise BoundaryInvalid(f"Redis blocker 非零：{name}")
    if execution and source["quarantined"] is not False:
        raise BoundaryInvalid("execution Redis quarantine 存在")
    raw_millis = text(source["observedAtMs"], "Redis observedAtMs", 32)
    if not raw_millis.isascii() or not raw_millis.isdecimal() or len(raw_millis) < 13:
        raise BoundaryInvalid("Redis observedAtMs 无效")
    return datetime.fromtimestamp(int(raw_millis) / 1000, tz=UTC)


def build_live(arguments: argparse.Namespace) -> dict[str, Any]:
    before, _ = load(arguments.topology_before)
    after, _ = load(arguments.topology_after)
    topology = validate_topology(before)
    if after != before:
        raise BoundaryInvalid("outer runtime topology 发生漂移")
    topology_sha = digest(canonical(topology)[:-1])
    schema_state = arguments.schema_state
    if schema_state in {"unmigrated", "migrated-empty-v2-closed"}:
        mode = "pre-contract" if schema_state == "unmigrated" else "post-contract-closed"
        if topology["core"]["schemaReady"] is not False:
            raise BoundaryInvalid("pre-activation Core schemaReady 必须为 false")
        pg_before, _ = load(arguments.postgres_before)
        pg_after, _ = load(arguments.postgres_after)
        expected_metrics = set(V1_POSTGRES_METRICS)
        if mode == "post-contract-closed":
            expected_metrics |= V2_POSTGRES_METRICS
        started, pg_identity = validate_pg_source(
            pg_before,
            expected_database=arguments.database,
            expected_metrics=expected_metrics,
        )
        finished, pg_identity_after = validate_pg_source(
            pg_after,
            expected_database=arguments.database,
            expected_metrics=expected_metrics,
        )
        if (
            pg_identity_after != pg_identity
            or finished < started
            or finished - started > MAX_WINDOW
        ):
            raise BoundaryInvalid("PostgreSQL identity 或采样窗口漂移")
        ordinary, _ = load(arguments.ordinary_redis)
        execution, _ = load(arguments.execution_redis)
        ordinary_at = validate_redis_source(ordinary, topology=topology, execution=False)
        execution_at = validate_redis_source(execution, topology=topology, execution=True)
        tolerance = timedelta(seconds=1)
        if not all(
            started - tolerance <= value <= finished + tolerance
            for value in (ordinary_at, execution_at)
        ):
            raise BoundaryInvalid("Redis 采样时间不在 PostgreSQL 稳定窗口")
        source_document = {
            "executionRedis": execution,
            "ordinaryRedis": ordinary,
            "postgresAfter": pg_after,
            "postgresBefore": pg_before,
        }
    else:
        if schema_state not in {"migrated-empty-v2", "migrated-with-v2"}:
            raise BoundaryInvalid("boundary schema state 无效")
        if topology["core"]["schemaReady"] is not True:
            raise BoundaryInvalid("migrated live drain 要求 schemaReady=true")
        report, _ = load(arguments.joint_report)
        normalized = validate_joint_report(report)
        if not normalized["v1DrainZero"] or not normalized["v2Converged"]:
            raise BoundaryInvalid("joint drain 非零")
        if normalized["database"] != arguments.database:
            raise BoundaryInvalid("joint drain 数据库漂移")
        if normalized["runtimeTopologySha256"] != topology_sha:
            raise BoundaryInvalid("joint drain 内外 topology 漂移")
        if normalized["coreRuntime"] != topology["core"]:
            raise BoundaryInvalid("joint drain Core identity 漂移")
        pg_identity = normalized["postgres"]["identity"]
        mode = "migrated"
        source_document = normalized
    return {
        "capturedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coreRuntime": topology["core"],
        "database": arguments.database,
        "executionRedisIdentity": topology["executionRedis"],
        "format": LIVE_FORMAT,
        "mode": mode,
        "postgresIdentity": pg_identity,
        "redisIdentity": topology["redis"],
        "runtimeTopologySha256": topology_sha,
        "schemaState": schema_state,
        "sourceReportSha256": digest(canonical(source_document)),
        "zeroDrain": True,
    }


def validate_live(document: dict[str, Any]) -> dict[str, Any]:
    live = exact(
        document,
        {
            "capturedAt",
            "coreRuntime",
            "database",
            "executionRedisIdentity",
            "format",
            "mode",
            "postgresIdentity",
            "redisIdentity",
            "runtimeTopologySha256",
            "schemaState",
            "sourceReportSha256",
            "zeroDrain",
        },
        "live drain",
    )
    if live["format"] != LIVE_FORMAT or live["zeroDrain"] is not True:
        raise BoundaryInvalid("live drain format/zero 无效")
    captured_at = instant(live["capturedAt"], "live drain capturedAt")
    if captured_at > datetime.now(UTC) + timedelta(seconds=1):
        raise BoundaryInvalid("live drain capturedAt 位于未来")
    topology = validate_topology(
        {
            "sourceVersion": "1",
            "core": live["coreRuntime"],
            "redis": live["redisIdentity"],
            "executionRedis": live["executionRedisIdentity"],
        }
    )
    exact(
        live["postgresIdentity"],
        {"databaseOid", "serverAddress", "serverPort", "serverVersionNum"},
        "PostgreSQL identity",
    )
    hex_value(live["runtimeTopologySha256"], HEX_64, "runtime topology SHA")
    hex_value(live["sourceReportSha256"], HEX_64, "source report SHA")
    expected_mode = {
        "unmigrated": "pre-contract",
        "migrated-empty-v2-closed": "post-contract-closed",
        "migrated-empty-v2": "migrated",
        "migrated-with-v2": "migrated",
    }.get(live["schemaState"])
    if live["mode"] != expected_mode:
        raise BoundaryInvalid("live drain mode/schemaState 不一致")
    if topology["core"]["schemaReady"] is not (live["mode"] == "migrated"):
        raise BoundaryInvalid("live drain Core schemaReady 与 profile 不一致")
    return live


def fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_no_replace(source: Path, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        if function is None:
            raise BoundaryInvalid("缺少 renameat2")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin":
        function = getattr(libc, "renamex_np", None)
        if function is None:
            raise BoundaryInvalid("缺少 renamex_np")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise BoundaryInvalid("平台不支持原子 no-replace")
    if result != 0:
        raise BoundaryInvalid(f"boundary evidence 原子发布失败：errno={ctypes.get_errno()}")


def validate_owner_arguments(arguments: argparse.Namespace) -> None:
    for value, pattern, label in (
        (arguments.lock_id, HEX_64, "lock ID"),
        (arguments.control_bundle_sha256, HEX_64, "control bundle SHA"),
        (arguments.manifest_sha256, HEX_64, "manifest SHA"),
        (arguments.boundary_helper_sha256, HEX_64, "boundary helper SHA"),
        (arguments.workflow_trusted_commit, HEX_40, "workflow trusted commit"),
        (arguments.target_release_commit, HEX_40, "target release commit"),
    ):
        hex_value(value, pattern, label)
    for value, label in (
        (arguments.run_id, "run ID"),
        (arguments.run_attempt, "run attempt"),
    ):
        if POSITIVE_DECIMAL.fullmatch(value) is None:
            raise BoundaryInvalid(f"{label} 无效")
    if BOUNDARY.fullmatch(text(arguments.boundary, "boundary", 64)) is None:
        raise BoundaryInvalid("boundary 名称无效")


def require_evidence_dir(path: Path) -> Path:
    directory = path.resolve(strict=True)
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise BoundaryInvalid("boundary evidence 目录无效")
    return directory


def issue(arguments: argparse.Namespace) -> tuple[Path, str, int]:
    live, payload = load(arguments.live_report)
    validate_live(live)
    if payload != canonical(live):
        raise BoundaryInvalid("live drain 不是 canonical JSON")
    if datetime.now(UTC) - instant(live["capturedAt"], "live drain capturedAt") > MAX_EVIDENCE_AGE:
        raise BoundaryInvalid("live drain 已超过一次性授权窗口")
    validate_owner_arguments(arguments)
    evidence_dir = require_evidence_dir(arguments.evidence_dir)
    boundary = arguments.boundary
    pattern = f"[0-9][0-9][0-9][0-9][0-9][0-9]-{boundary}.*.json"
    if any(evidence_dir.glob(pattern)):
        raise BoundaryInvalid("该 boundary 已签发；claimed outcome-unknown 禁止重试")
    sequence_path = evidence_dir / "sequence"
    if sequence_path.exists():
        if sequence_path.is_symlink() or stat.S_IMODE(sequence_path.stat().st_mode) != 0o600:
            raise BoundaryInvalid("boundary sequence 文件无效")
        raw_sequence = sequence_path.read_text(encoding="ascii").strip()
        if not raw_sequence.isdecimal() or raw_sequence.startswith("0"):
            raise BoundaryInvalid("boundary sequence 无效")
        sequence = int(raw_sequence) + 1
    else:
        sequence = 1
    issued_at = datetime.now(UTC)
    document = {
        "boundary": boundary,
        "boundaryHelperSha256": arguments.boundary_helper_sha256,
        "controlBundleSha256": arguments.control_bundle_sha256,
        "expiresAt": (issued_at + MAX_EVIDENCE_AGE).isoformat().replace("+00:00", "Z"),
        "format": EVIDENCE_FORMAT,
        "issuedAt": issued_at.isoformat().replace("+00:00", "Z"),
        "liveDrain": live,
        "liveDrainSha256": digest(payload),
        "lockId": arguments.lock_id,
        "manifestSha256": arguments.manifest_sha256,
        "runAttempt": arguments.run_attempt,
        "runId": arguments.run_id,
        "sequence": sequence,
        "targetReleaseCommit": arguments.target_release_commit,
        "workflowTrustedCommit": arguments.workflow_trusted_commit,
    }
    evidence_payload = canonical(document)
    ready = evidence_dir / f"{sequence:06d}-{boundary}.ready.json"
    descriptor = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(evidence_payload)
        output.flush()
        os.fsync(output.fileno())
    sequence_temp = evidence_dir / ".sequence.partial"
    descriptor = os.open(sequence_temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as output:
        output.write(f"{sequence}\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(sequence_temp, sequence_path)
    fsync_path(evidence_dir)
    return ready, digest(evidence_payload), sequence


def validate_evidence(
    document: dict[str, Any],
    payload: bytes,
    arguments: argparse.Namespace,
    *,
    require_fresh: bool,
) -> None:
    exact(document, EVIDENCE_KEYS, "boundary evidence")
    if document["format"] != EVIDENCE_FORMAT:
        raise BoundaryInvalid("boundary evidence format 无效")
    live = document["liveDrain"]
    if not isinstance(live, dict):
        raise BoundaryInvalid("live drain 字段无效")
    validate_live(live)
    if digest(canonical(live)) != document["liveDrainSha256"]:
        raise BoundaryInvalid("live drain SHA 漂移")
    if payload != canonical(document) or digest(payload) != arguments.expected_sha256:
        raise BoundaryInvalid("boundary evidence SHA 漂移")
    expected = {
        "boundary": arguments.boundary,
        "boundaryHelperSha256": arguments.boundary_helper_sha256,
        "controlBundleSha256": arguments.control_bundle_sha256,
        "lockId": arguments.lock_id,
        "manifestSha256": arguments.manifest_sha256,
        "runAttempt": arguments.run_attempt,
        "runId": arguments.run_id,
        "targetReleaseCommit": arguments.target_release_commit,
        "workflowTrustedCommit": arguments.workflow_trusted_commit,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise BoundaryInvalid("boundary evidence owner/provenance 漂移")
    issued_at = instant(document["issuedAt"], "boundary issuedAt")
    expires_at = instant(document["expiresAt"], "boundary expiresAt")
    if expires_at - issued_at != MAX_EVIDENCE_AGE:
        raise BoundaryInvalid("boundary evidence 有效期无效")
    now = datetime.now(UTC)
    if require_fresh and not (issued_at <= now < expires_at):
        raise BoundaryInvalid("boundary evidence 已过期或尚未生效")


def consume(arguments: argparse.Namespace) -> tuple[Path, str]:
    validate_owner_arguments(arguments)
    evidence_dir = require_evidence_dir(arguments.evidence_dir)
    ready = arguments.ready_file.resolve(strict=True)
    if ready.parent != evidence_dir or not ready.name.endswith(".ready.json"):
        raise BoundaryInvalid("ready evidence 路径越界")
    document, payload = load(ready)
    validate_evidence(document, payload, arguments, require_fresh=True)
    claimed = ready.with_name(ready.name.removesuffix(".ready.json") + ".claimed.json")
    publish_no_replace(ready, claimed)
    fsync_path(evidence_dir)
    return claimed, digest(payload)


def mark_applied(arguments: argparse.Namespace) -> tuple[Path, str]:
    validate_owner_arguments(arguments)
    evidence_dir = require_evidence_dir(arguments.evidence_dir)
    claimed = arguments.claimed_file.resolve(strict=True)
    if claimed.parent != evidence_dir or not claimed.name.endswith(".claimed.json"):
        raise BoundaryInvalid("claimed evidence 路径越界")
    document, payload = load(claimed)
    validate_evidence(document, payload, arguments, require_fresh=False)
    applied = claimed.with_name(claimed.name.removesuffix(".claimed.json") + ".applied.json")
    applied_document = {
        "boundary": document["boundary"],
        "evidenceSha256": digest(payload),
        "format": APPLIED_FORMAT,
        "lockId": document["lockId"],
        "outcome": arguments.outcome,
        "sequence": document["sequence"],
    }
    if applied.exists():
        existing, existing_payload = load(applied)
        if existing != applied_document or existing_payload != canonical(applied_document):
            raise BoundaryInvalid("既有 applied boundary 漂移")
        return applied, digest(existing_payload)
    partial = evidence_dir / f".{applied.name}.partial"
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(canonical(applied_document))
        output.flush()
        os.fsync(output.fileno())
    try:
        publish_no_replace(partial, applied)
    finally:
        if partial.exists():
            partial.unlink()
    fsync_path(evidence_dir)
    return applied, digest(canonical(applied_document))


def build_ledger(arguments: argparse.Namespace) -> tuple[dict[str, Any], str]:
    evidence_dir = require_evidence_dir(arguments.evidence_dir)
    hex_value(arguments.lock_id, HEX_64, "lock ID")
    unexpected = [
        path.name
        for path in evidence_dir.iterdir()
        if path.name != "sequence"
        and re.fullmatch(r"[0-9]{6}-.+\.(?:claimed|applied)\.json", path.name) is None
    ]
    if unexpected:
        raise BoundaryInvalid("boundary ledger 存在 ready/partial/未知文件")
    claimed_paths = sorted(evidence_dir.glob("*.claimed.json"))
    applied_paths = sorted(evidence_dir.glob("*.applied.json"))
    if len(claimed_paths) != len(applied_paths):
        raise BoundaryInvalid("存在 claimed outcome-unknown boundary，禁止提交")
    entries: list[dict[str, Any]] = []
    for ordinal, claimed in enumerate(claimed_paths, start=1):
        document, payload = load(claimed)
        if payload != canonical(document) or set(document) != EVIDENCE_KEYS:
            raise BoundaryInvalid("claimed boundary 无效")
        if document["lockId"] != arguments.lock_id or document["sequence"] != ordinal:
            raise BoundaryInvalid("boundary ledger 顺序/lock 漂移")
        applied = claimed.with_name(
            claimed.name.removesuffix(".claimed.json") + ".applied.json"
        )
        applied_document, applied_payload = load(applied)
        exact(
            applied_document,
            {"boundary", "evidenceSha256", "format", "lockId", "outcome", "sequence"},
            "applied boundary",
        )
        expected_applied = {
            "boundary": document["boundary"],
            "evidenceSha256": digest(payload),
            "format": APPLIED_FORMAT,
            "lockId": arguments.lock_id,
            "outcome": applied_document["outcome"],
            "sequence": ordinal,
        }
        if applied_payload != canonical(applied_document) or applied_document != expected_applied:
            raise BoundaryInvalid("applied boundary 漂移")
        if applied_document["outcome"] not in {"succeeded", "compensated"}:
            raise BoundaryInvalid("applied boundary outcome 无效")
        entries.append(
            {
                "boundary": document["boundary"],
                "evidenceSha256": digest(payload),
                "outcome": applied_document["outcome"],
                "sequence": ordinal,
            }
        )
    ledger = {"entries": entries, "format": LEDGER_FORMAT, "lockId": arguments.lock_id}
    payload = canonical(ledger)
    return ledger, digest(payload)


def add_owner_arguments(target: argparse.ArgumentParser) -> None:
    for name in (
        "boundary",
        "lock-id",
        "control-bundle-sha256",
        "manifest-sha256",
        "run-id",
        "run-attempt",
        "boundary-helper-sha256",
        "workflow-trusted-commit",
        "target-release-commit",
    ):
        target.add_argument(f"--{name}", required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    actions = root.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build-live")
    build.add_argument("--database", required=True)
    build.add_argument("--schema-state", required=True)
    build.add_argument("--topology-before", type=Path, required=True)
    build.add_argument("--topology-after", type=Path, required=True)
    build.add_argument("--postgres-before", type=Path)
    build.add_argument("--postgres-after", type=Path)
    build.add_argument("--ordinary-redis", type=Path)
    build.add_argument("--execution-redis", type=Path)
    build.add_argument("--joint-report", type=Path)
    verify = actions.add_parser("verify-live")
    verify.add_argument("--live-report", type=Path, required=True)
    issue_parser = actions.add_parser("issue")
    issue_parser.add_argument("--live-report", type=Path, required=True)
    issue_parser.add_argument("--evidence-dir", type=Path, required=True)
    add_owner_arguments(issue_parser)
    consume_parser = actions.add_parser("consume")
    consume_parser.add_argument("--evidence-dir", type=Path, required=True)
    consume_parser.add_argument("--ready-file", type=Path, required=True)
    consume_parser.add_argument("--expected-sha256", required=True)
    add_owner_arguments(consume_parser)
    applied_parser = actions.add_parser("mark-applied")
    applied_parser.add_argument("--evidence-dir", type=Path, required=True)
    applied_parser.add_argument("--claimed-file", type=Path, required=True)
    applied_parser.add_argument("--expected-sha256", required=True)
    applied_parser.add_argument(
        "--outcome", choices=("succeeded", "compensated"), required=True
    )
    add_owner_arguments(applied_parser)
    ledger_parser = actions.add_parser("ledger")
    ledger_parser.add_argument("--evidence-dir", type=Path, required=True)
    ledger_parser.add_argument("--lock-id", required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.action == "build-live":
            print(canonical(build_live(arguments)).decode("utf-8"), end="")
        elif arguments.action == "verify-live":
            document, payload = load(arguments.live_report)
            validate_live(document)
            if payload != canonical(document):
                raise BoundaryInvalid("live drain 不是 canonical JSON")
            print(f"live-drain-ok:{digest(payload)}")
        elif arguments.action == "issue":
            ready, evidence_sha, sequence = issue(arguments)
            print(f"boundary-evidence-ready:{sequence}:{evidence_sha}:{ready}")
        elif arguments.action == "consume":
            claimed, evidence_sha = consume(arguments)
            print(f"boundary-evidence-claimed:{evidence_sha}:{claimed}")
        elif arguments.action == "mark-applied":
            applied, applied_sha = mark_applied(arguments)
            print(f"boundary-evidence-applied:{applied_sha}:{applied}")
        else:
            ledger, ledger_sha = build_ledger(arguments)
            print(canonical(ledger).decode("utf-8"), end="")
            print(f"boundary-ledger-sha256:{ledger_sha}", file=sys.stderr)
        return 0
    except BoundaryInvalid as error:
        print(f"release-boundary:error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
